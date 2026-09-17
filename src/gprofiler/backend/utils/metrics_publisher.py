"""
Metrics Publisher - Singleton class for publishing metrics to metrics agent.

This module provides a thread-safe singleton class for publishing SLI (Service Level
Indicator) metrics to a metrics agent for monitoring and alerting.

Metric Types:
    - SLI Metrics (Primary): Track success/failure rates for SLO monitoring
    - Error Metrics: Available for operational error tracking (not currently used)

Usage:
    # Initialize once (typically in main application startup)
    metrics_publisher = MetricsPublisher(
        server_url="tcp://localhost:18126",
        service_name="gprofiler-backend",
        sli_metric_uuid="your-uuid-here",
        enabled=True
    )
    
    # Use anywhere in your code - get_instance() always returns valid object
    MetricsPublisher.get_instance().send_sli_metric(
        "success", 
        "profile_upload", 
        {"service": "devapp"}
    )
"""

import logging
import socket
import threading
import time
from typing import Dict, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class MetricCategory(str, Enum):
    """Categories for error metrics - Backend specific"""
    API = "api"                          # API endpoint errors
    DATABASE = "database"                # Database connection/query errors
    STORAGE = "storage"                  # S3/SQS storage errors
    AUTHENTICATION = "authentication"    # Auth/API key validation errors
    EXTERNAL_SERVICE = "external_service"  # Calls to external services (if any)


# Constants for SLI response types
RESPONSE_TYPE_SUCCESS = "success"
RESPONSE_TYPE_FAILURE = "failure"
RESPONSE_TYPE_IGNORED_FAILURE = "ignored_failure"


class NoopMetricsPublisher:
    """
    No-op metrics publisher for graceful degradation.
    Used when MetricsPublisher is not initialized. All methods do nothing.
    Matches agent's pattern for handling uninitialized state.
    """
    def send_error_metric(self, *args, **kwargs) -> bool:
        return False
    
    def send_sli_metric(self, *args, **kwargs) -> bool:
        return False
    
    def flush_and_close(self):
        pass


class MetricsPublisher:
    """
    Thread-safe singleton class for publishing metrics to a metrics agent.
    
    Supports two types of metrics:
    1. SLI Metrics (Primary): Service Level Indicator tracking for SLO monitoring
       Pattern: error-budget.counters.{uuid}{response_type=*, method_name=*}
       
    2. Error Metrics: Operational error tracking (available but not currently used)
       Pattern: gprofiler.{category}.{error_type}.error
    """
    
    _instance: Optional['MetricsPublisher'] = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Thread-safe singleton implementation"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(MetricsPublisher, cls).__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        server_url: str = "tcp://localhost:18126",
        service_name: str = "gprofiler-backend",
        sli_metric_uuid: Optional[str] = None,
        enabled: bool = True
    ):
        """
        Initialize MetricsPublisher with configuration.
        
        Args:
            server_url: TCP endpoint URL for metrics agent (default: tcp://localhost:18126)
            service_name: Service name for metric tagging
            sli_metric_uuid: UUID for SLI metrics (required for SLI tracking)
            enabled: Whether metrics publishing is enabled
        """
        # Only initialize once (singleton pattern)
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self._enabled = enabled
        self._service_name = service_name
        self._server_url = server_url
        self._sli_metric_uuid = sli_metric_uuid
        self._connection_failed = False
        self._last_error_log_time = 0
        self._error_log_interval = 300  # Log connection errors at most once per 5 minutes
        
        # Parse server URL (only matters if enabled)
        if server_url.startswith('tcp://'):
            url_parts = server_url[6:].split(':')
            self.host = url_parts[0]
            self.port = int(url_parts[1]) if len(url_parts) > 1 else 18126
        else:
            # If disabled, don't raise error for invalid URL
            if enabled:
                raise ValueError(f"Unsupported server URL format: {server_url}")
            else:
                self.host = "localhost"
                self.port = 18126
        
        if enabled:
            logger.info(
                f"MetricsPublisher initialized: service={service_name}, "
                f"server={self.host}:{self.port}, sli_enabled={sli_metric_uuid is not None}"
            )
        else:
            logger.info("MetricsPublisher disabled")
    
    @classmethod
    def get_instance(cls) -> 'MetricsPublisher':
        """
        Get the MetricsPublisher singleton instance.
        
        Returns the instance even if disabled - methods check _enabled internally.
        get_instance() is always safe to call.
        
        Returns:
            MetricsPublisher instance (or NoopMetricsPublisher if not initialized)
        """
        if cls._instance is None:
            # Return noop instance if not initialized (graceful degradation)
            return NoopMetricsPublisher()
        
        return cls._instance
    
    def _send_metric(self, metric_line: str) -> bool:
        """
        Send a metric line to the metrics agent using TCP socket.
        
        Args:
            metric_line: Formatted metric string
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self._enabled or not self.host or not self.port:
            return False
        
        try:
            # Create TCP connection and send metric (agent pattern)
            with socket.create_connection((self.host, self.port), timeout=1.0) as sock:
                # Ensure message ends with newline
                message = metric_line if metric_line.endswith('\n') else metric_line + '\n'
                sock.sendall(message.encode('utf-8'))
            
            # Reset connection failed flag on success
            if self._connection_failed:
                self._connection_failed = False
                logger.info("Metrics agent connection restored")
            
            return True
            
        except Exception as e:
            # Rate-limit error logging to avoid log spam
            current_time = time.time()
            if not self._connection_failed or (current_time - self._last_error_log_time) > self._error_log_interval:
                logger.warning(f"Failed to send metric: {e}")
                self._last_error_log_time = current_time
                self._connection_failed = True
            
            return False
    
    def send_error_metric(
        self,
        category: str,
        error_type: str,
        tags: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send an operational error metric.
        
        Pattern: gprofiler.{category}.{error_type}.error
        
        Args:
            category: Error category (e.g., "api", "database", "storage", "authentication")
            error_type: Specific error type (e.g., "connection_failed", "timeout")
            tags: Optional tags to include with the metric (e.g., {"endpoint": "/api/profiles"})
            
        Returns:
            True if sent successfully, False otherwise
            
        Example:
            # Backend-specific error metrics
            publisher.send_error_metric("database", "connection_timeout", {"host": "db-primary"})
            publisher.send_error_metric("storage", "s3_upload_failed", {"bucket": "profiles"})
            publisher.send_error_metric("api", "endpoint_timeout", {"endpoint": "/api/v2/profiles"})
        """
        if not self._enabled:
            return False
        
        # Build metric name
        metric_name = f"gprofiler.{category}.{error_type}.error"
        
        # Get current epoch timestamp
        timestamp = int(time.time())
        
        # Build tag string (Graphite plaintext protocol format)
        tag_parts = [f"service={self._service_name}"]
        if tags:
            for key, value in tags.items():
                tag_parts.append(f"{key}={value}")
        tag_string = " ".join(tag_parts)
        
        # Format: put metric_name timestamp value tag1=value1 tag2=value2 ...
        metric_line = f"put {metric_name} {timestamp} 1 {tag_string}"
        
        logger.debug(f"Sending error metric: {metric_line}")
        return self._send_metric(metric_line)
    
    def send_sli_metric(
        self,
        response_type: str,
        method_name: str,
        extra_tags: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send an SLI (Service Level Indicator) metric for SLO tracking.
        
        Pattern: error-budget.counters.{uuid}{response_type=*, method_name=*}
        
        Args:
            response_type: Type of response ("success", "failure", "ignored_failure")
            method_name: Name of the method/operation (e.g., "profile_upload", "send_heartbeat")
            extra_tags: Optional additional tags (matches agent parameter name)
            
        Returns:
            True if sent successfully, False otherwise
            
        Example:
            # Backend SLI metrics
            publisher.send_sli_metric("success", "profile_upload", {"service": "devapp"})
            publisher.send_sli_metric("failure", "send_heartbeat", {"status_code": 500})
            publisher.send_sli_metric("ignored_failure", "profile_upload", {"reason": "authentication_failed"})
        """
        if not self._enabled or not self._sli_metric_uuid:
            return False
        
        # Build metric name using configured SLI UUID
        # Format: error-budget.counters.{uuid}
        # Example: error-budget.counters.test-sli-uuid-12345
        metric_name = f"error-budget.counters.{self._sli_metric_uuid}"
        
        # Get current epoch timestamp
        timestamp = int(time.time())
        
        # Build tag string with required SLI tags (Graphite plaintext protocol format)
        tag_parts = [
            f"service={self._service_name}",
            f"response_type={response_type}",
            f"method_name={method_name}"
        ]
        
        if extra_tags:
            for key, value in extra_tags.items():
                tag_parts.append(f"{key}={value}")
        
        tag_string = " ".join(tag_parts)
        
        # Format: put metric_name timestamp value tag1=value1 tag2=value2 ...
        metric_line = f"put {metric_name} {timestamp} 1 {tag_string}"
        
        # Log at INFO level for verification (shows actual metric being sent)
        logger.info(f"📊 Sending SLI metric: {metric_line}")
        return self._send_metric(metric_line)
    
    def flush_and_close(self):
        """
        Flush any pending metrics and close the publisher.
        
        Note: Backend sends metrics synchronously over TCP (no buffering),
        so there's nothing to flush, but we keep the method name consistent
        with the agent's interface for easier code review.
        
        This should be called during application shutdown.
        """
        with self._lock:
            logger.info("MetricsPublisher closed")
            self._enabled = False
    
    def __del__(self):
        """Cleanup on deletion"""
        try:
            self.flush_and_close()
        except Exception:
            pass  # Ignore errors during cleanup


# Convenience functions for common use cases
def send_error_metric(category: str, error_type: str, tags: Optional[Dict[str, Any]] = None) -> bool:
    """
    Convenience function to send an error metric.
    
    Usage:
        from backend.utils.metrics_publisher import send_error_metric
        send_error_metric("database", "connection_failed", {"host": "db-1"})
    """
    return MetricsPublisher.get_instance().send_error_metric(category, error_type, tags)


def send_sli_metric(response_type: str, method_name: str, extra_tags: Optional[Dict[str, Any]] = None) -> bool:
    """
    Convenience function to send an SLI metric.
    
    Usage:
        from backend.utils.metrics_publisher import send_sli_metric
        send_sli_metric("success", "profile_upload", {"service": "devapp"})
    """
    return MetricsPublisher.get_instance().send_sli_metric(response_type, method_name, extra_tags)


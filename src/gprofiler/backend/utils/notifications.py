"""
Slack notification utilities for sending messages to Slack channels.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from ..config import SLACK_BOT_TOKEN, SLACK_CHANNELS, DEFAULT_SLACK_CHANNELS


logger = logging.getLogger(__name__)


class SlackNotifier:
    """
    A utility class for sending notifications to Slack channels using the Slack SDK.
    
    This class provides methods to send various types of messages to Slack channels,
    including basic text messages and rich messages with blocks and attachments.
    """
    
    def __init__(self, token: Optional[str] = None, default_channel: Optional[str] = None):
        """
        Initialize the SlackNotifier with a bot token.
        
        Args:
            token: Slack bot token (starts with 'xoxb-'). If not provided, reads from SLACK_BOT_TOKEN environment variable.
            default_channel: Default channel to send messages to (e.g., '#general', '@user', 'C1234567890').
                           If not provided, uses the first channel from SLACK_CHANNELS config.
        """
        # Use provided token or fall back to config
        bot_token = token or SLACK_BOT_TOKEN
        
        if not bot_token:
            raise ValueError("Slack bot token must be provided either as parameter or via SLACK_BOT_TOKEN environment variable")
        
        self.client = WebClient(token=bot_token)
        
        # Set default channel - use provided, or first from config, or fallback to hardcoded default
        if default_channel:
            self.default_channel = default_channel
        elif SLACK_CHANNELS:
            self.default_channel = SLACK_CHANNELS[0].strip()
        else:
            self.default_channel = DEFAULT_SLACK_CHANNELS[0]
        
        # Test the connection
        try:
            response = self.client.auth_test()
            logger.info(f"Connected to Slack as {response['user']}")
        except SlackApiError as e:
            logger.error(f"Failed to authenticate with Slack: {e.response['error']}")
            raise
    
    def send_message(
        self, 
        text: str, 
        channel: Optional[str] = None, 
        thread_ts: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send a basic text message to a Slack channel.
        
        Args:
            text: The message text to send
            channel: Target channel (uses default_channel if not provided)
            thread_ts: Timestamp of parent message to reply in thread
            **kwargs: Additional arguments to pass to the Slack API
            
        Returns:
            Dict containing the Slack API response
            
        Raises:
            SlackApiError: If the Slack API returns an error
            ValueError: If no channel is specified and no default channel is set
        """
        target_channel = channel or self.default_channel
        if not target_channel:
            raise ValueError("No channel specified and no default channel set")
        
        try:
            response = self.client.chat_postMessage(
                channel=target_channel,
                text=text,
                thread_ts=thread_ts,
                **kwargs
            )
            logger.info(f"Message sent successfully to {target_channel}")
            return response
        except SlackApiError as e:
            logger.error(f"Failed to send message to {target_channel}: {e.response['error']}")
            raise
    
    def send_rich_message(
        self,
        blocks: List[Dict[str, Any]] = None,
        attachments: List[Dict[str, Any]] = None,
        text: str = "",
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send a rich message with blocks and/or attachments to a Slack channel.
        
        Args:
            blocks: List of block elements for rich formatting
            attachments: List of legacy attachments
            text: Fallback text for notifications
            channel: Target channel (uses default_channel if not provided)
            thread_ts: Timestamp of parent message to reply in thread
            **kwargs: Additional arguments to pass to the Slack API
            
        Returns:
            Dict containing the Slack API response
            
        Raises:
            SlackApiError: If the Slack API returns an error
            ValueError: If no channel is specified and no default channel is set
        """
        target_channel = channel or self.default_channel
        if not target_channel:
            raise ValueError("No channel specified and no default channel set")
        
        try:
            response = self.client.chat_postMessage(
                channel=target_channel,
                text=text,
                blocks=blocks,
                attachments=attachments,
                thread_ts=thread_ts,
                **kwargs
            )
            logger.info(f"Rich message sent successfully to {target_channel}")
            return response
        except SlackApiError as e:
            logger.error(f"Failed to send rich message to {target_channel}: {e.response['error']}")
            raise
    
    def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "info",
        channel: Optional[str] = None,
        additional_fields: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Send an alert message with consistent formatting.
        
        Args:
            title: Alert title
            message: Alert message body
            severity: Alert severity ('info', 'warning', 'error', 'success')
            channel: Target channel (uses default_channel if not provided)
            additional_fields: Additional fields to include in the alert
            
        Returns:
            Dict containing the Slack API response
        """
        # Color mapping for different severities
        color_map = {
            "info": "#36a64f",      # Green
            "warning": "#ff9900",   # Orange
            "error": "#ff0000",     # Red
            "success": "#36a64f"    # Green
        }
        
        color = color_map.get(severity, "#36a64f")
        
        # Build attachment fields
        fields = []
        if additional_fields:
            fields = [
                {"title": key, "value": value, "short": True}
                for key, value in additional_fields.items()
            ]
        
        attachments = [{
            "color": color,
            "title": title,
            "text": message,
            "fields": fields,
            "footer": "gProfiler Performance Studio",
            "ts": int(__import__('time').time())
        }]
        
        return self.send_rich_message(
            attachments=attachments,
            text=f"{title}: {message}",
            channel=channel
        )
    
    def send_performance_alert(
        self,
        service_name: str,
        metric_name: str,
        current_value: Union[str, float],
        threshold: Union[str, float],
        severity: str = "warning",
        channel: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a performance-related alert with structured data.
        
        Args:
            service_name: Name of the service experiencing issues
            metric_name: Name of the performance metric
            current_value: Current value of the metric
            threshold: Threshold that was exceeded
            severity: Alert severity level
            channel: Target channel (uses default_channel if not provided)
            
        Returns:
            Dict containing the Slack API response
        """
        title = f"Performance Alert: {service_name}"
        message = f"Metric `{metric_name}` has exceeded threshold"
        
        additional_fields = {
            "Service": service_name,
            "Metric": metric_name,
            "Current Value": str(current_value),
            "Threshold": str(threshold),
            "Severity": severity.upper()
        }
        
        return self.send_alert(
            title=title,
            message=message,
            severity=severity,
            channel=channel,
            additional_fields=additional_fields
        )
    
    def update_message(
        self,
        ts: str,
        channel: str,
        text: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Update an existing message.
        
        Args:
            ts: Timestamp of the message to update
            channel: Channel containing the message
            text: New text content
            blocks: New block elements
            attachments: New attachments
            
        Returns:
            Dict containing the Slack API response
        """
        try:
            response = self.client.chat_update(
                ts=ts,
                channel=channel,
                text=text,
                blocks=blocks,
                attachments=attachments
            )
            logger.info(f"Message updated successfully in {channel}")
            return response
        except SlackApiError as e:
            logger.error(f"Failed to update message in {channel}: {e.response['error']}")
            raise
    
    def delete_message(self, ts: str, channel: str) -> Dict[str, Any]:
        """
        Delete a message.
        
        Args:
            ts: Timestamp of the message to delete
            channel: Channel containing the message
            
        Returns:
            Dict containing the Slack API response
        """
        try:
            response = self.client.chat_delete(ts=ts, channel=channel)
            logger.info(f"Message deleted successfully from {channel}")
            return response
        except SlackApiError as e:
            logger.error(f"Failed to delete message from {channel}: {e.response['error']}")
            raise
    
    def get_available_channels(self) -> List[str]:
        """
        Get the list of available channels from configuration.
        
        Returns:
            List of channel names configured via SLACK_CHANNELS environment variable
            or the default channels if not configured.
        """
        return [channel.strip() for channel in SLACK_CHANNELS if channel.strip()]
    
    def is_valid_channel(self, channel: str) -> bool:
        """
        Check if a channel is in the list of available channels.
        
        Args:
            channel: Channel name to validate
            
        Returns:
            True if channel is in the available channels list, False otherwise
        """
        available_channels = self.get_available_channels()
        return channel in available_channels
    
    def send_to_all_channels(
        self, 
        text: str, 
        thread_ts: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Send a message to all configured channels.
        
        Args:
            text: The message text to send
            thread_ts: Timestamp of parent message to reply in thread
            **kwargs: Additional arguments to pass to the Slack API
            
        Returns:
            List of responses from each channel
            
        Raises:
            SlackApiError: If the Slack API returns an error for any channel
        """
        responses = []
        available_channels = self.get_available_channels()
        
        for channel in available_channels:
            try:
                response = self.send_message(
                    text=text,
                    channel=channel,
                    thread_ts=thread_ts,
                    **kwargs
                )
                responses.append(response)
            except SlackApiError as e:
                logger.error(f"Failed to send message to {channel}: {e.response['error']}")
                # Continue with other channels even if one fails
                responses.append({"error": str(e), "channel": channel})
        
        return responses
    
    def send_rich_message_to_all_channels(
        self,
        blocks: List[Dict[str, Any]] = None,
        attachments: List[Dict[str, Any]] = None,
        text: str = "",
        thread_ts: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Send a rich message with blocks and/or attachments to all configured channels.
        
        Args:
            blocks: List of block elements for rich formatting
            attachments: List of legacy attachments
            text: Fallback text for notifications
            thread_ts: Timestamp of parent message to reply in thread
            **kwargs: Additional arguments to pass to the Slack API
            
        Returns:
            List of responses from each channel
            
        Raises:
            SlackApiError: If the Slack API returns an error for any channel
        """
        responses = []
        available_channels = self.get_available_channels()
        
        for channel in available_channels:
            try:
                response = self.send_rich_message(
                    blocks=blocks,
                    attachments=attachments,
                    text=text,
                    channel=channel,
                    thread_ts=thread_ts,
                    **kwargs
                )
                responses.append(response)
            except SlackApiError as e:
                logger.error(f"Failed to send rich message to {channel}: {e.response['error']}")
                # Continue with other channels even if one fails
                responses.append({"error": str(e), "channel": channel})
        
        return responses

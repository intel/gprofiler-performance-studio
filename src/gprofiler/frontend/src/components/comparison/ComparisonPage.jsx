{
    /*
     * Copyright (C) 2023 Intel Corporation
     *
     * Licensed under the Apache License, Version 2.0 (the "License");
     * you may not use this file except in compliance with the License.
     * You may obtain a copy of the License at
     *
     *    http://www.apache.org/licenses/LICENSE-2.0
     *
     * Unless required by applicable law or agreed to in writing, software
     * distributed under the License is distributed on an "AS IS" BASIS,
     * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
     * See the License for the specific language governing permissions and
     * limitations under the License.
     */
}

import { Box, Grow, Typography } from '@mui/material';
import _ from 'lodash';
import { memo, useContext, useEffect, useState } from 'react';

import useGetCompareFgData from '../../api/hooks/useGetCompareFgData';
import useGetFgData from '../../api/hooks/useGetFgData';
import useGetServicesList from '../../api/hooks/useGetServicesList';
import useServicePickQueryParams from '../../hooks/useServicePickQueryParams';
import useTimePickQueryParams from '../../hooks/useTimePickQueryParams';
import { SelectorsContext } from '../../states';
import { FgContext } from '../../states';
import { CompareEmptyState } from '../../svg';
import { DEFAULT_INITIAL_TIME_RANGE_FILTER, getUpdatedFgData } from '../../utils/fgUtils';
import Flexbox from '../common/layout/Flexbox';
import FGLoader from '../profiles/FGLoader';
import NoServices from '../profiles/NoServices';
import CompareTable from './CompareTable';
import ComparisonFunctionGraph from './ComparisonFunctionGraph';
import ComparisonHeader from './header/ComparisonHeader';
import ComparisonTopPanel from './header/ComparisonTopPanel';

const ComparisonPage = memo(() => {
    const { services, areServicesLoading, absoluteTimeSelection } = useContext(SelectorsContext);

    const { setFgOriginData, setIsFgDisplayed, setIsFgLoading } = useContext(FgContext);

    const { selectedService: compareService, setSelectedService: setCompareService } = useServicePickQueryParams({
        services,
        customParam: 'cService',
    });

    const [compareTimeSelection, setCompareTimeSelectionState] = useState({
        relativeTime: DEFAULT_INITIAL_TIME_RANGE_FILTER,
    });

    const [absoluteCompareTime, setAbsoluteCompareTime] = useState({ cStartTime: '', cEndTime: '' });

    const setCompareTimeSelection = useTimePickQueryParams({
        setTimeSelection: setCompareTimeSelectionState,
        timeSelection: compareTimeSelection,
        customQueryParams: { time: 'cTime', start: 'cStartTime', end: 'cEndTime' },
    });

    const [compareFgData, setCompareFgData] = useState([]);

    const { data, error, loading } = useGetFgData({
        disableLastWeekFetch: true,
    });

    const { compareData, isCompareLoading } = useGetCompareFgData({
        timeSelection: compareTimeSelection,
        service: compareService,
        setAbsoluteCompareTime,
    });

    useEffect(() => {
        if (compareData) {
            setCompareFgData(getUpdatedFgData(compareData));
        }
    }, [compareData]);

    const isFgDisplayed = !error && !loading && data && (!!data?.value || !!compareData?.value);

    useEffect(() => {
        if (!loading && data) {
            setFgOriginData(getUpdatedFgData(data));
        }
    }, [data, loading, setFgOriginData]);

    useEffect(() => {
        setIsFgDisplayed(isFgDisplayed);
        setIsFgLoading(loading);
    }, [setIsFgDisplayed, isFgDisplayed, setIsFgLoading, loading]);

    useGetServicesList({ disableAutoSelection: true });

    const hasNoServices = _.isEmpty(services);

    const [functionName, setFunctionName] = useState('');

    return (
        <Box sx={{ backgroundColor: 'white.main', height: '100%' }}>
            <ComparisonHeader
                isGrayedOut={areServicesLoading || hasNoServices}
                compareTimeSelection={compareTimeSelection}
                setCompareTimeSelection={setCompareTimeSelection}
                compareSamples={compareData?.value}
                isCompareDataLoading={isCompareLoading}
                isDataLoading={loading}
                setCompareService={setCompareService}
                compareService={compareService}
            />
            <Flexbox column sx={{ minHeight: '30%' }}>
                <ComparisonTopPanel
                    absoluteTimeSelection={absoluteTimeSelection}
                    absoluteCompareTime={absoluteCompareTime}
                />

                {areServicesLoading ? (
                    <FGLoader />
                ) : hasNoServices ? (
                    <NoServices />
                ) : (
                    <>
                        {loading ? (
                            <FGLoader />
                        ) : (
                            <>
                                {!isFgDisplayed ? (
                                    <Flexbox
                                        column
                                        justifyContent='center'
                                        alignItems='center'
                                        sx={{ height: '100%', pt: 9 }}>
                                        <Typography variant='h4'>Time comparison</Typography>
                                        <Typography variant='body3' sx={{ textAlign: 'center', pt: 3, pb: 7 }}>
                                            Compare between different times of the same service to evaluate changes over
                                            time.
                                            <br /> To start, choose a service and a time frame.
                                        </Typography>
                                        <CompareEmptyState />
                                    </Flexbox>
                                ) : (
                                    <Flexbox
                                        column
                                        spacing={2}
                                        sx={{
                                            height: 'fit-content',
                                        }}>
                                        {functionName && (
                                            <Grow in={Boolean(functionName)}>
                                                <Box>
                                                    <ComparisonFunctionGraph
                                                        functionName={functionName}
                                                        setFunctionName={setFunctionName}
                                                        compareService={compareService}
                                                        compareTimeSelection={compareTimeSelection}
                                                    />
                                                </Box>
                                            </Grow>
                                        )}
                                        <CompareTable
                                            compareFgData={compareFgData}
                                            isLoading={loading || isCompareLoading}
                                            functionName={functionName}
                                            setFunctionName={setFunctionName}
                                        />
                                    </Flexbox>
                                )}
                            </>
                        )}
                    </>
                )}
            </Flexbox>
        </Box>
    );
});
ComparisonPage.displayName = 'ComparisonPage';
export default ComparisonPage;

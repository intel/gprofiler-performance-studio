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

import 'chartjs-adapter-date-fns';

import { CategoryScale, Chart as ChartJS, LinearScale, LineElement, PointElement, TimeScale, Tooltip } from 'chart.js';
import zoomPlugin from 'chartjs-plugin-zoom';
import { useEffect, useState } from 'react';
import { Line } from 'react-chartjs-2';

import { calcGraphData, calcGraphOptions } from './graphUtils';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, TimeScale, zoomPlugin);

const CpiCountGraph = ({ data, edges, setZoomedTime }) => {
    const [parsedData, setParsedData] = useState(calcGraphData(data, edges, 'avg_cpi_count', 'max_cpi_count'));
    const [options, setOptions] = useState(calcGraphOptions(data, setZoomedTime));

    useEffect(() => {
        setParsedData(calcGraphData(data, edges, 'avg_cpi_count', 'max_cpi_count'));
        setOptions(calcGraphOptions(data, setZoomedTime));
    }, [data, edges, setZoomedTime]);

    return <Line options={options} data={parsedData} />;
};

export default CpiCountGraph;

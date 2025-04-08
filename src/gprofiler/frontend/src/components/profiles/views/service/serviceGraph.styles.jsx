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

import TabList from '@mui/lab/TabList';
import TabPanel from '@mui/lab/TabPanel';
import { Tab } from '@mui/material';
import { styled } from '@mui/material/styles';

import { COLORS } from '@/theme/colors';

export const StyledTabs = styled(TabList)({
    minHeight: '40px !important',
    '& .MuiTabs-indicator': {
        display: 'flex',
        justifyContent: 'center',
        backgroundColor: COLORS.BLACK,
    },
});

export const StyledTab = styled(Tab)(({ theme }) => ({
    ...theme.typography.caption1,
    color: theme.palette.grey.dark,
    minHeight: '40px !important',
    minWidth: '30px',
    fontSize: '14px',
    padding: '0 10px',
    '&.Mui-selected': {
        color: COLORS.BLACK,
    },
}));

export const StyledTabPanel = styled(TabPanel)({
    height: '220px',
    padding: 0,
});

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

import { ListItemIcon, ListItemText } from '@mui/material';
import MenuItem from '@mui/material/MenuItem';
import { stringify } from 'query-string';
import { useCallback, useContext, useRef, useState } from 'react';
import { useLocation } from 'react-router';

import Tooltip from '@/components/common/dataDisplay/muiToolTip/Tooltip';
import DotsMenu from '@/components/common/dotsMenu/DotsMenu';
import { COPY_ONLY_IN_HTTPS } from '@/utils/consts';
import { isPathSecure } from '@/utils/generalUtils';

import { DATA_URLS } from '../../../api/urls';
import { getStartEndDateTimeFromSelection } from '../../../api/utils';
import { FgContext, SelectorsContext } from '../../../states';
import { FilterTagsContext } from '../../../states/filters/FiltersTagsContext';
import { COLORS } from '../../../theme/colors';
import { buildAbsolutePermaLink } from '../../../utils/fgUtils';
import Icon from '../../common/icon/Icon';
import { ICONS_NAMES } from '../../common/icon/iconsData';

const DownloadLink = ({ serviceName, timeSelection, activeFilters, fileType, downloadRef }) => {
    const timeParams = getStartEndDateTimeFromSelection(timeSelection);

    return (
        <a
            href={`${DATA_URLS.DOWNLOAD_FLAMEGRAPH}${fileType}/?${stringify({
                serviceName,
                ...timeParams,
                filter: JSON.stringify(activeFilters),
            })}`}
            className='download-svg-link'
            style={{ display: 'none' }}
            ref={downloadRef}
            rel='noopener noreferrer'>
            {''}
        </a>
    );
};

const ProfilesActions = ({ isGrayedOut }) => {
    const [anchorEl, setAnchorEl] = useState(null);

    const { isFgDisplayed } = useContext(FgContext);
    const { timeSelection, selectedService, ignoreZeros, setIgnoreZeros, absoluteTimeSelection } =
        useContext(SelectorsContext);
    const { activeFilterTag } = useContext(FilterTagsContext);

    const { search } = useLocation();

    const handleClose = useCallback(() => {
        setAnchorEl(null);
    }, [setAnchorEl]);

    const downloadSvgRef = useRef(null);

    const onClickDownloadSvg = useCallback(() => {
        if (isFgDisplayed && downloadSvgRef.current) {
            downloadSvgRef.current.click();
        }
        handleClose();
    }, [handleClose, isFgDisplayed]);

    const onCopyPermalinkClick = (e) => {
        if (isPathSecure()) {
            const permaLink = buildAbsolutePermaLink(absoluteTimeSelection, search);
            navigator.clipboard.writeText(permaLink);
        }
        setAnchorEl(null);
    };

    const onClickIgnoreZeros = () => {
        setIgnoreZeros(!ignoreZeros);
    };

    return (
        <>
            <DotsMenu disabled={isGrayedOut} customEnchorEl={anchorEl} setCustomEnchorEl={setAnchorEl}>
                {isFgDisplayed && (
                    <MenuItem onClick={onClickDownloadSvg}>
                        <ListItemIcon>
                            <Icon name={ICONS_NAMES.Download} color={COLORS.BLUE_7} />
                        </ListItemIcon>
                        <ListItemText>Download Flame Graph</ListItemText>
                    </MenuItem>
                )}

                <Tooltip placement='left' content='When calculating cores & nodes averages ignore values that are zero'>
                    <MenuItem key='ignoreZeros' onClick={onClickIgnoreZeros}>
                        <ListItemIcon>
                            <Icon
                                name={ignoreZeros ? ICONS_NAMES.CheckBoxMarked : ICONS_NAMES.CheckBoxBlank}
                                color={ignoreZeros ? COLORS.PRIMARY_PURPLE : COLORS.BLUE_7}
                            />
                        </ListItemIcon>
                        <ListItemText>Zero values ignored</ListItemText>
                    </MenuItem>
                </Tooltip>

                <Tooltip placement='left' content={!isPathSecure() ? COPY_ONLY_IN_HTTPS : 'Copy permalink'}>
                    <MenuItem onClick={onCopyPermalinkClick}>
                        <ListItemIcon>
                            <Icon name={ICONS_NAMES.Copy} color={COLORS.BLUE_7} />
                        </ListItemIcon>
                        <ListItemText> Copy permalink </ListItemText>
                    </MenuItem>
                </Tooltip>
            </DotsMenu>

            {isFgDisplayed && (
                <DownloadLink
                    serviceName={selectedService}
                    timeSelection={timeSelection}
                    activeFilters={activeFilterTag}
                    fileType='svg'
                    downloadRef={downloadSvgRef}
                />
            )}
        </>
    );
};

export default ProfilesActions;

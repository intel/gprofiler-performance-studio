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

import { Box, ListItemButton, ListItemIcon, Menu } from '@mui/material';
import _ from 'lodash';
import { useContext, useState } from 'react';
import { useLocation } from 'react-router-dom';

import Button from '@/components/common/button/Button';
import Icon from '@/components/common/icon/Icon';
import { ICONS_NAMES } from '@/components/common/icon/iconsData';
import Flexbox from '@/components/common/layout/Flexbox';
import { isFilterTypeExist } from '@/components/filters/utils';
import { FgContext, SelectorsContext } from '@/states';
import { FilterTagsContext } from '@/states/filters/FiltersTagsContext';
import { COLORS } from '@/theme/colors';
import { PROFILES_VIEWS } from '@/utils/consts';
import { FILTER_TYPES } from '@/utils/filtersUtils';

import ViewModeTooltip from './ViewModeTooltip';

const VIEW_TO_ICON_NAME = {
    [PROFILES_VIEWS.flamegraph]: ICONS_NAMES.FlameGraphView,
    [PROFILES_VIEWS.table]: ICONS_NAMES.TableView,
    [PROFILES_VIEWS.service]: ICONS_NAMES.ServiceView,
    [PROFILES_VIEWS.html]: ICONS_NAMES.LastHtmlView,
    [PROFILES_VIEWS.adhoc]: ICONS_NAMES.FlameGraphView, // Reuse flamegraph icon for now
};

const ToolTipWrappingThing = ({ viewMode, onChooseView }) => {
    const { search, pathname } = useLocation();
    const safeViewMode = encodeURIComponent(viewMode);

    let baseUrl = `${window.location.protocol}//${window.location.host}${pathname}`;
    const url = new URL(baseUrl);

    if (search) {
        // Remove the leading '?' from the search string before appending
        url.search = search.substring(1);
    }

    url.searchParams.set('view', safeViewMode);

    return (
        <ViewModeTooltip viewMode={viewMode}>
            <ListItemButton
                component='a'
                onClick={(e) => onChooseView(e, viewMode)}
                sx={{ margin: 0, px: 3, py: 3, '&:hover': { backgroundColor: 'hoverGrey.main' } }}
                href={url.toString()}>
                <ListItemIcon sx={{ minWidth: '10px !important' }}>
                    <Icon
                        name={VIEW_TO_ICON_NAME[viewMode]}
                        color={viewMode !== viewMode ? COLORS.WHITE : COLORS.SECONDARY_ORANGE}
                        vertical
                        width={22}
                        height={14}
                    />
                </ListItemIcon>
            </ListItemButton>
        </ViewModeTooltip>
    );
};

const ViewModeSwitch = () => {
    const { viewMode, setViewMode, areServicesLoading } = useContext(SelectorsContext);
    const { isFgDisplayed, isFgLoading } = useContext(FgContext);
    const { activeFilterTag } = useContext(FilterTagsContext);
    const isHostNameFilterActive = isFilterTypeExist(FILTER_TYPES.HostName.value, activeFilterTag);
    const profilesViewsToDisplay = _.omitBy(
        PROFILES_VIEWS,
        (view) => !isHostNameFilterActive && view === PROFILES_VIEWS.html
    );

    const disabled = isFgLoading || areServicesLoading || (!isFgDisplayed && !activeFilterTag);

    const [anchor, setAnchor] = useState(null);
    const [mainClicked, setMainClicked] = useState(null);

    const handleClick = (event, type) => {
        if (type === 'main') {
            setMainClicked(true);
        } else {
            setMainClicked(false);
        }
        setAnchor(event.currentTarget);
    };

    const handleClose = () => {
        setAnchor(null);
    };

    const onChooseView = (e, view) => {
        e.preventDefault();
        setViewMode(view);
        handleClose();
    };
    const open = Boolean(anchor);
    return (
        <>
            <Flexbox alignItems='center' spacing={0} justifyContent='start'>
                <ViewModeTooltip viewMode={disabled ? '' : viewMode}>
                    <Box sx={{ lineHeight: 'initial' }}>
                        <Button
                            iconOnly
                            color='inherit'
                            disabled={disabled}
                            onClick={(event) => handleClick(event, 'main')}
                            sxOverrides={{
                                borderRadius: '2px 0 0 2px',
                                backgroundColor: 'grey.dark',
                                px: 3,
                                '&:hover': {
                                    backgroundColor: 'grey.dark',
                                },
                            }}>
                            <Icon
                                name={VIEW_TO_ICON_NAME[viewMode]}
                                color={COLORS.WHITE}
                                hoverColor={COLORS.SECONDARY_ORANGE}
                                width={22}
                                height={14}
                            />
                        </Button>
                    </Box>
                </ViewModeTooltip>
                <Button
                    iconOnly
                    color='inherit'
                    disabled={disabled}
                    onClick={(event) => handleClick(event, 'arrow')}
                    sxOverrides={{
                        borderRadius: '0 2px 2px 0',
                        backgroundColor: 'primary.main',
                        width: '20px',
                        height: '30px !important',
                        px: 0,
                        '&:hover': {
                            backgroundColor: 'primary.main',
                        },
                    }}>
                    <Icon
                        name={ICONS_NAMES.ChevronDown}
                        flip={open}
                        color={COLORS.WHITE}
                        hoverColor={COLORS.SECONDARY_ORANGE}
                    />
                </Button>
            </Flexbox>
            <Menu
                anchorEl={anchor}
                open={open}
                onClose={handleClose}
                PaperProps={{ sx: { backgroundColor: 'grey.dark', borderRadius: '2px' } }}
                MenuListProps={{ sx: { p: 0 } }}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}
                transformOrigin={{
                    vertical: 'top',
                    horizontal: mainClicked ? 'left' : 'right',
                }}>
                {Object.keys(profilesViewsToDisplay).map((view) => (
                    <ToolTipWrappingThing key={view} viewMode={view} onChooseView={onChooseView} />
                ))}
            </Menu>
        </>
    );
};

export default ViewModeSwitch;

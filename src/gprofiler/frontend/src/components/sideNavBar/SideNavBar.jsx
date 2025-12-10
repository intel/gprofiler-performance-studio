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

import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import List from '@mui/material/List';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import { Link, useLocation } from 'react-router-dom';

import { GprofilerLogo, GprofilerLogoWhiteText } from '../../svg';
import { ComparisonPageIcon, DocumentationIcon, OverviewPageIcon, ProfilesPageIcon } from '../../svg/sideMenuIcons';
import { COLORS } from '../../theme/colors';
import { EXTERNAL_URLS, PAGES } from '../../utils/consts';
import { useFullScreenContext } from '../../utils/contexts';
import Button from '../common/button/Button';
import Icon from '../common/icon/Icon';
import { ICONS_NAMES } from '../common/icon/iconsData';
import Flexbox from '../common/layout/Flexbox';
import { SideBarItem, SideBarTooltip, StyledDrawer } from './sideNavBar.styles';

let navigationItems = [
    {
        key: PAGES.overview.key,
        label: PAGES.overview.label,
        to: PAGES.overview.to,
        icon: <OverviewPageIcon fill={COLORS.SILVER_GREY} />,
        selectedIcon: <OverviewPageIcon />,
    },
    {
        key: PAGES.profiles.key,
        label: PAGES.profiles.label,
        to: PAGES.profiles.to,
        icon: <ProfilesPageIcon fill={COLORS.SILVER_GREY} />,
        selectedIcon: <ProfilesPageIcon />,
    },
    {
        key: PAGES.profiling.key,
        label: PAGES.profiling.label,
        to: PAGES.profiling.to,
        icon: <Icon name={ICONS_NAMES.Crosshairs} color={COLORS.SILVER_GREY} />,
        selectedIcon: <Icon name={ICONS_NAMES.Crosshairs} color={COLORS.PRIMARY_BLUE} />,
    },
    {
        key: PAGES.comparison.key,
        label: PAGES.comparison.label,
        to: PAGES.comparison.to,
        icon: <ComparisonPageIcon fill={COLORS.SILVER_GREY} />,
        selectedIcon: <ComparisonPageIcon />,
    },
];

const SideNavBar = ({ onSidebarToggle, isCollapsed }) => {
    const { isFullScreen } = useFullScreenContext();
    const location = useLocation();

    const isExpanded = !isCollapsed;

    if (isFullScreen) return null;
    else
        return (
            <>
                <StyledDrawer variant='permanent' sx={{ zIndex: 50 }} open={isExpanded}>
                    <Link to={PAGES.welcome.to}>
                        <Box
                            sx={{
                                width: isExpanded ? '130px' : '100%',
                                padding: '15px 0',
                                display: 'flex',
                                justifyContent: 'center',
                                alignItems: 'center',
                                svg: {
                                    height: '25px',
                                },
                            }}>
                            {isExpanded ? <GprofilerLogoWhiteText /> : <GprofilerLogo />}
                        </Box>
                    </Link>

                    <Divider variant='middle' sx={{ borderColor: COLORS.BLUE_8 }} />
                    <List>
                        {navigationItems.map((item) => (
                            <SideBarTooltip title={isExpanded ? '' : item.label} key={item.key}>
                                <SideBarItem
                                    sx={{ px: isExpanded ? 5 : 6 }}
                                    selected={location.pathname === item.to}
                                    component={item.key === 'profiling' ? 'a' : Link}
                                    href={item.key === 'profiling' ? '/profiling' : undefined}
                                    to={item.key === 'profiling' ? undefined : item.to}>
                                    <ListItemIcon sx={{ minWidth: '35px' }}>
                                        {location.pathname === item.to ? item.selectedIcon : item.icon}
                                    </ListItemIcon>
                                    {isExpanded && <ListItemText sx={{ margin: 0 }} primary={item.label} />}
                                </SideBarItem>
                            </SideBarTooltip>
                        ))}
                    </List>

                    <Flexbox
                        column
                        justifyContent='flex-end'
                        sx={{
                            height: '100%',
                        }}>
                        <SideBarTooltip title={isExpanded ? '' : PAGES.installation.label}>
                            <Box sx={{ px: 2 }}>
                                <AddServiceButton
                                    to={PAGES.installation.to}
                                    iconOnly={!isExpanded}
                                    startIcon={<Icon name={ICONS_NAMES.Plus} color={COLORS.WHITE} size={30} />}>
                                    {PAGES.installation.label}
                                </AddServiceButton>
                            </Box>
                        </SideBarTooltip>

                        <SideBarTooltip title={isExpanded ? '' : 'Documentation'}>
                            <span>
                                <MenuButton
                                    href={EXTERNAL_URLS.documentation.to}
                                    iconOnly={!isExpanded}
                                    startIcon={<DocumentationIcon />}>
                                    Documentation
                                </MenuButton>
                            </span>
                        </SideBarTooltip>

                        <SideBarTooltip title={isExpanded ? '' : 'Github'}>
                            <span>
                                <MenuButton
                                    href={EXTERNAL_URLS.github.to}
                                    iconOnly={!isExpanded}
                                    startIcon={<Icon name={ICONS_NAMES.GitHub} color={COLORS.SILVER_GREY} />}>
                                    Github
                                </MenuButton>
                            </span>
                        </SideBarTooltip>

                        <Divider variant='middle' sx={{ borderColor: COLORS.BLUE_8, py: 2 }} />

                        <Button
                            iconOnly
                            onClick={() => onSidebarToggle(!isCollapsed)}
                            sxOverrides={isCollapsed ? {} : { alignSelf: 'flex-end' }}>
                            <Icon
                                name={ICONS_NAMES.ChevronDoubleRight}
                                size={25}
                                color={COLORS.SILVER_GREY}
                                flip={!isCollapsed}
                            />
                        </Button>
                    </Flexbox>
                </StyledDrawer>
            </>
        );
};
export default SideNavBar;

const MenuButton = ({ children, startIcon, iconOnly, ...props }) => (
    <Button
        variant='text'
        sx={{
            minWidth: '59px',
            fontWeight: 400,
            color: COLORS.GREY_2,
            '&:hover': {
                color: COLORS.WHITE,
            },
            '&.Mui-disabled': {
                color: COLORS.GREY_4,
            },
            ml: iconOnly ? 0 : 3,
            mt: iconOnly ? 4 : 2,
        }}
        startIcon={iconOnly ? undefined : startIcon}
        {...props}>
        {iconOnly ? startIcon : children}
    </Button>
);

const AddServiceButton = ({ children, startIcon, iconOnly, ...props }) => (
    <Button
        color='primary'
        sxOverrides={{
            p: iconOnly ? '1px' : '',
            borderRadius: 1,
            fontWeight: 400,
            marginLeft: iconOnly ? '10px' : '',
            color: COLORS.WHITE,
            mt: iconOnly ? 5 : 1,
            pl: iconOnly ? '' : 0,
            '&.Mui-disabled': {
                color: COLORS.GREY_4,
            },
        }}
        fullWidth
        iconOnly={iconOnly}
        startIcon={iconOnly ? undefined : startIcon}
        {...props}>
        {iconOnly ? startIcon : children}
    </Button>
);

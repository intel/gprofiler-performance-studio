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

import { FormControl } from '@mui/material';
import _ from 'lodash';
import { useContext } from 'react';

import { FILTER_TAGS_ACTIONS, FilterTagsContext } from '../../../states/filters/FiltersTagsContext';
import { COLORS } from '../../../theme/colors';
import { FILTER_EQUALNESS, FILTER_OPERATIONS, FILTER_TYPES } from '../../../utils/filtersUtils';
import Icon from '../../common/icon/Icon';
import { ICONS_NAMES } from '../../common/icon/iconsData';
import Flexbox from '../../common/layout/Flexbox';
import FilterOptionsSelect from '../select/FilterOptionsSelect';
import FiltersSelect from '../select/FiltersSelect';
import FiltersSelectItem from '../select/FiltersSelectItem';
import { FiltersIconButton } from '../styles';
import useHoverState from '../useHoverState';
import { shouldShowFilterTypeOptions } from '../utils';
import FilterFormActions from './FilterFormActions';

const FilterForm = ({ postCreateCallback, onClose, valueOptions, valueOptionsLoading }) => {
    const { filter, dispatchFilterTags } = useContext(FilterTagsContext);
    const { hoveredItemId, onMouseEnter, onMouseLeave } = useHoverState();

    const onDeleteFilterClick = (index) => {
        dispatchFilterTags({ type: FILTER_TAGS_ACTIONS.DELETE, index });
    };

    const onFilterTypeChange = (index) => async (e) => {
        dispatchFilterTags({ type: FILTER_TAGS_ACTIONS.TYPE_CHANGE, index, payload: e.target.value });
    };

    const onFilterValueChange = (index) => (newValue) => {
        dispatchFilterTags({ type: FILTER_TAGS_ACTIONS.VALUE_CHANGE, index, payload: newValue });
    };

    const onIsOperatorChange = (index) => (e) => {
        dispatchFilterTags({ type: FILTER_TAGS_ACTIONS.EQ_CHANGE, index, payload: e.target.value });
    };

    const onOperatorChange = () => (e) => {
        dispatchFilterTags({ type: FILTER_TAGS_ACTIONS.OPERATION_CHANGE, payload: e.target.value });
    };

    const [operation, rules] = Object.entries(filter.filter)[0];

    return (
        <Flexbox direction='column' spacing={5}>
            {(rules || []).map((FilterItem, index) => {
                const [type, subItem] = Object.entries(FilterItem)[0];
                const [equal, value] = Object.entries(subItem)[0];
                return (
                    <Flexbox
                        spacing={3}
                        key={index}
                        onMouseEnter={() => {
                            onMouseEnter(index);
                        }}
                        onMouseLeave={() => {
                            onMouseLeave(index);
                        }}>
                        {index > 0 && (
                            <FormControl>
                                <FiltersSelect
                                    width={72}
                                    value={operation}
                                    disabled={index > 1}
                                    defaultValue={FILTER_OPERATIONS.$and.value}
                                    onChange={onOperatorChange()}>
                                    {Object.values(FILTER_OPERATIONS).map((operationType) => (
                                        <FiltersSelectItem
                                            key={operationType.value}
                                            value={operationType.value}
                                            label={operationType.display}>
                                            {operationType.display}
                                        </FiltersSelectItem>
                                    ))}
                                </FiltersSelect>
                            </FormControl>
                        )}
                        <FormControl>
                            <FiltersSelect
                                value={type}
                                renderValue={(value) => (value ? FILTER_TYPES[value].display : 'Type')}
                                label='Type'
                                width={180}
                                onChange={onFilterTypeChange(index)}>
                                {Object.values(FILTER_TYPES).map((type) => (
                                    <FiltersSelectItem
                                        key={type.display}
                                        description={type.description}
                                        disabled={
                                            !shouldShowFilterTypeOptions(filter, {
                                                type: type.value,
                                                operator: operation,
                                            })
                                        }
                                        value={type.value || ''}
                                        label={type.display}>
                                        {type.display}
                                    </FiltersSelectItem>
                                ))}
                            </FiltersSelect>
                        </FormControl>

                        <FormControl>
                            <FiltersSelect width={80} value={equal} onChange={onIsOperatorChange(index)}>
                                {Object.values(FILTER_EQUALNESS).map((equalType) => (
                                    <FiltersSelectItem
                                        key={equalType.value}
                                        value={equalType.value}
                                        description={equalType.display}
                                        label={equalType.display}>
                                        {equalType.display}
                                    </FiltersSelectItem>
                                ))}
                            </FiltersSelect>
                        </FormControl>
                        <FormControl>
                            <FilterOptionsSelect
                                value={value || ''}
                                options={valueOptions[type]}
                                freeSolo={equal === FILTER_EQUALNESS.$like.value}
                                disabled={
                                    valueOptionsLoading[type] ||
                                    (equal !== FILTER_EQUALNESS.$like.value && _.isEmpty(valueOptions[type]))
                                }
                                loading={valueOptionsLoading[type]}
                                onChange={onFilterValueChange(index)}
                            />
                        </FormControl>

                        {hoveredItemId === index && rules?.length > 1 && (
                            <FiltersIconButton onClick={() => onDeleteFilterClick(index)} tooltipText='Delete rule'>
                                <Icon color={COLORS.DARK_PURPLE} size={15} name={ICONS_NAMES.Close} />
                            </FiltersIconButton>
                        )}
                    </Flexbox>
                );
            })}
            <FilterFormActions postCreateCallback={postCreateCallback} onClose={onClose} />
        </Flexbox>
    );
};

export default FilterForm;

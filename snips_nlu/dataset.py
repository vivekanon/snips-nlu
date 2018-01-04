from __future__ import unicode_literals

import json
from copy import deepcopy

from nlu_utils import normalize
from semantic_version import Version

from snips_nlu.builtin_entities import is_builtin_entity
from snips_nlu.constants import (TEXT, USE_SYNONYMS, SYNONYMS, DATA, INTENTS,
                                 ENTITIES, ENTITY, SLOT_NAME, UTTERANCES,
                                 LANGUAGE, VALUE, AUTOMATICALLY_EXTENSIBLE,
                                 SNIPS_NLU_VERSION, CAPITALIZE,
                                 NORMALIZED_TEXT)
from snips_nlu.languages import Language
from snips_nlu.string_variations import get_string_variations
from snips_nlu.tokenization import tokenize_light
from snips_nlu.utils import validate_type, validate_key, validate_keys


def extract_queries_entities(dataset):
    entities_values = {ent_name: [] for ent_name in dataset[ENTITIES]}

    for intent in dataset[INTENTS].values():
        for query in intent[UTTERANCES]:
            for chunk in query[DATA]:
                if ENTITY in chunk and not is_builtin_entity(chunk[ENTITY]):
                    entities_values[chunk[ENTITY]].append(chunk[TEXT])
    return {k: list(v) for k, v in entities_values.iteritems()}


def validate_and_format_dataset(dataset, capitalization_threshold=.1):
    dataset = deepcopy(dataset)
    dataset = json.loads(json.dumps(dataset))
    validate_type(dataset, dict)
    mandatory_keys = [INTENTS, ENTITIES, LANGUAGE, SNIPS_NLU_VERSION]
    for key in mandatory_keys:
        validate_key(dataset, key, object_label="dataset")
    Version(dataset[SNIPS_NLU_VERSION])  # Check that the version is semantic
    validate_type(dataset[ENTITIES], dict)
    validate_type(dataset[INTENTS], dict)
    validate_type(dataset[LANGUAGE], basestring)
    language = Language.from_iso_code(dataset[LANGUAGE])

    for intent in dataset[INTENTS].values():
        validate_and_format_intent(intent, dataset[ENTITIES])

    queries_entities_values = extract_queries_entities(dataset)

    for entity_name, entity in dataset[ENTITIES].iteritems():
        if is_builtin_entity(entity_name):
            dataset[ENTITIES][entity_name] = \
                validate_and_format_builtin_entity(entity)
        else:
            dataset[ENTITIES][entity_name] = validate_and_format_custom_entity(
                entity, queries_entities_values[entity_name], language,
                capitalization_threshold)

    return dataset


def validate_and_format_intent(intent, entities):
    validate_type(intent, dict)
    validate_key(intent, UTTERANCES, object_label="intent dict")
    validate_type(intent[UTTERANCES], list)
    for utterance in intent[UTTERANCES]:
        validate_type(utterance, dict)
        validate_key(utterance, DATA, object_label="utterance")
        validate_type(utterance[DATA], list)
        for chunk in utterance[DATA]:
            validate_type(chunk, dict)
            validate_key(chunk, TEXT, object_label="chunk")
            if NORMALIZED_TEXT in chunk:
                validate_type(chunk[NORMALIZED_TEXT], (str, unicode))
                chunk[TEXT] = chunk[NORMALIZED_TEXT]
                chunk.pop(NORMALIZED_TEXT)
            if ENTITY in chunk or SLOT_NAME in chunk:
                mandatory_keys = [ENTITY, SLOT_NAME]
                validate_keys(chunk, mandatory_keys, object_label="chunk")
                if is_builtin_entity(chunk[ENTITY]):
                    continue
                else:
                    validate_key(entities, chunk[ENTITY],
                                 object_label=ENTITIES)
    return intent


def get_text_from_chunks(chunks):
    return ''.join(chunk[TEXT] for chunk in chunks)


def capitalization_ratio(entity_utterances, language):
    capitalizations = []
    for utterance in entity_utterances:
        tokens = tokenize_light(utterance, language)
        for t in tokens:
            if t.isupper() or t.istitle():
                capitalizations.append(1.0)
            else:
                capitalizations.append(0.0)
    if not capitalizations:
        return 0
    return sum(capitalizations) / float(len(capitalizations))


def add_variation_if_needed(utterances, variation, utterance, language):
    if not variation:
        return utterances
    normalized_variation = normalize(variation)
    all_variations = get_string_variations(
        variation, language)
    all_variations.update(
        get_string_variations(normalized_variation, language))
    for v in all_variations:
        if v not in utterances:
            utterances[v] = utterance
    return utterances


def validate_and_format_custom_entity(entity, queries_entities, language,
                                      capitalization_threshold):
    validate_type(entity, dict)
    mandatory_keys = [USE_SYNONYMS, AUTOMATICALLY_EXTENSIBLE, DATA]
    validate_keys(entity, mandatory_keys, object_label="entity")
    validate_type(entity[USE_SYNONYMS], bool)
    validate_type(entity[AUTOMATICALLY_EXTENSIBLE], bool)
    validate_type(entity[DATA], list)

    formatted_entity = dict()
    formatted_entity[AUTOMATICALLY_EXTENSIBLE] = entity[
        AUTOMATICALLY_EXTENSIBLE]
    use_synonyms = entity[USE_SYNONYMS]

    # Validate format and filter out unused data
    valid_entity_data = []
    for entry in entity[DATA]:
        validate_type(entry, dict)
        validate_keys(entry, [VALUE, SYNONYMS], object_label="entity entry")
        entry[VALUE] = entry[VALUE].strip()
        if not entry[VALUE]:
            continue
        validate_type(entry[SYNONYMS], list)
        entry[SYNONYMS] = [s.strip() for s in entry[SYNONYMS]
                           if len(s.strip()) > 0]
        valid_entity_data.append(entry)
    entity[DATA] = valid_entity_data

    # Compute capitalization before normalizing
    # Normalization lowercase and hence lead to bad capitalization calculation
    if use_synonyms:
        entities = [s for entry in entity[DATA]
                    for s in entry[SYNONYMS] + [entry[VALUE]]]
    else:
        entities = [entry[VALUE] for entry in entity[DATA]]
    ratio = capitalization_ratio(entities + queries_entities, language)
    formatted_entity[CAPITALIZE] = ratio > capitalization_threshold

    # Normalize
    normalize_data = dict()
    for entry in entity[DATA]:
        entry_value = entry[VALUE]
        normalize_data = add_variation_if_needed(
            normalize_data, entry_value, entry_value, language)

        if use_synonyms:
            for s in entry[SYNONYMS]:
                normalize_data = add_variation_if_needed(
                    normalize_data, s, entry_value, language)

    formatted_entity[UTTERANCES] = normalize_data
    # Merge queries_entities
    for value in queries_entities:
        formatted_entity = add_entity_value_if_missing(
            value, formatted_entity, language)

    return formatted_entity


def validate_and_format_builtin_entity(entity):
    validate_type(entity, dict)
    return entity


def add_entity_value_if_missing(value, entity, language):
    entity[UTTERANCES] = add_variation_if_needed(entity[UTTERANCES], value,
                                                 value, language)
    return entity

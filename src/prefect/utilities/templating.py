import enum
import re
from typing import TYPE_CHECKING, Any, Dict, NamedTuple, Set, Type, TypeVar, Union

from prefect.client.utilities import inject_client
from prefect.utilities.annotations import NotSet

if TYPE_CHECKING:
    from prefect.client.orchestration import PrefectClient


T = TypeVar("T", str, int, float, bool, dict, list, None)

PLACEHOLDER_CAPTURE_REGEX = re.compile(r"({{\s*([\w\.-]+)\s*}})")
BLOCK_DOCUMENT_PLACEHOLDER_PREFIX = "prefect.blocks."


class PlaceholderType(enum.Enum):
    STANDARD = "standard"
    BLOCK_DOCUMENT = "block_document"


class Placeholder(NamedTuple):
    full_match: str
    name: str
    type: PlaceholderType


def determine_placeholder_type(name: str) -> PlaceholderType:
    """
    Determines the type of a placeholder based on its name.

    Args:
        name: The name of the placeholder

    Returns:
        The type of the placeholder
    """
    if name.startswith(BLOCK_DOCUMENT_PLACEHOLDER_PREFIX):
        return PlaceholderType.BLOCK_DOCUMENT
    return PlaceholderType.STANDARD


def find_placeholders(template: T) -> Set[Placeholder]:
    """
    Finds all placeholders in a template.

    Args:
        template: template to discover placeholders in

    Returns:
        A set of all placeholders in the template
    """
    if isinstance(template, (int, float, bool)):
        return set()
    if isinstance(template, str):
        result = PLACEHOLDER_CAPTURE_REGEX.findall(template)
        return {
            Placeholder(full_match, name, determine_placeholder_type(name))
            for full_match, name in result
        }
    elif isinstance(template, dict):
        return set().union(
            *[find_placeholders(value) for key, value in template.items()]
        )
    elif isinstance(template, list):
        return set().union(*[find_placeholders(item) for item in template])
    else:
        raise ValueError(f"Unexpected type: {type(template)}")


def apply_values(template: T, values: Dict[str, Any]) -> Union[T, Type[NotSet]]:
    """
    Replaces placeholders in a template with values from a supplied dictionary.

    Will recursively replace placeholders in dictionaries and lists.

    If a value has no placeholders, it will be returned unchanged.

    If a template contains only a single placeholder, the placeholder will be
    fully replaced with the value.

    If a template contains text before or after a placeholder or there are
    multiple placeholders, the placeholders will be replaced with the
    corresponding variable values.

    If a template contains a placeholder that is not in `values`, UNSET will
    be returned to signify that no placeholder replacement occurred. If
    `template` is a dictionary that contains a key with a value of UNSET,
    the key will be removed in the return value.

    Args:
        template: template to discover and replace values in
        values: The values to apply to placeholders in the template

    Returns:
        The template with the values applied
    """
    if isinstance(template, (int, float, bool, type(NotSet), type(None))):
        return template
    if isinstance(template, str):
        placeholders = find_placeholders(template)
        if not placeholders:
            # If there are no values, we can just use the template
            return template
        elif (
            len(placeholders) == 1
            and list(placeholders)[0].full_match == template
            and list(placeholders)[0].type is PlaceholderType.STANDARD
        ):
            # If there is only one variable with no surrounding text,
            # we can replace it. If there is no variable value, we
            # return UNSET to indicate that the value should not be included.
            return values.get(list(placeholders)[0].name, NotSet)
        else:
            for full_match, name, placeholder_type in placeholders:
                if (
                    name in values
                    and values[name] is not None
                    and placeholder_type is PlaceholderType.STANDARD
                ):
                    template = template.replace(full_match, str(values.get(name, "")))
            return template
    elif isinstance(template, dict):
        updated_template = {}
        for key, value in template.items():
            updated_value = apply_values(value, values)
            if updated_value is not NotSet:
                updated_template[key] = updated_value

        return updated_template
    elif isinstance(template, list):
        updated_list = []
        for value in template:
            updated_value = apply_values(value, values)
            if updated_value is not NotSet:
                updated_list.append(updated_value)
        return updated_list
    else:
        raise ValueError(f"Unexpected template type {type(template).__name__!r}")


@inject_client
async def resolve_block_document_references(
    template: T, client: "PrefectClient" = None
) -> Union[T, Dict[str, Any]]:
    """
    Resolve block document references in a template by replacing each reference with
    the data of the block document.

    Recursively searches for block document references in dictionaries and lists.

    Identifies block document references by the as dictionary with the following
    structure:
    ```
    {
        "$ref": {
            "block_document_id": <block_document_id>
        }
    }
    ```
    where `<block_document_id>` is the ID of the block document to resolve.

    Once the block document is retrieved from the API, the data of the block document
    is used to replace the reference.

    Args:
        template: The template to resolve block documents in

    Returns:
        The template with block documents resolved
    """
    if isinstance(template, dict):
        block_document_id = template.get("$ref", {}).get("block_document_id")
        if block_document_id:
            block_document = await client.read_block_document(block_document_id)
            return block_document.data
        updated_template = {}
        for key, value in template.items():
            updated_value = await resolve_block_document_references(value)
            updated_template[key] = updated_value
        return updated_template
    elif isinstance(template, list):
        return [
            await resolve_block_document_references(item, client=client)
            for item in template
        ]
    elif isinstance(template, str):
        placeholders = find_placeholders(template)
        has_block_document_placeholder = any(
            placeholder.type is PlaceholderType.BLOCK_DOCUMENT
            for placeholder in placeholders
        )
        if len(placeholders) == 0 or not has_block_document_placeholder:
            return template
        elif (
            len(placeholders) == 1
            and list(placeholders)[0].full_match == template
            and list(placeholders)[0].type is PlaceholderType.BLOCK_DOCUMENT
        ):
            block_type_slug, block_document_name = (
                list(placeholders)[0]
                .name.replace(BLOCK_DOCUMENT_PLACEHOLDER_PREFIX, "")
                .split(".")
            )
            block_document = await client.read_block_document_by_name(
                name=block_document_name, block_type_slug=block_type_slug
            )
            return block_document.data
        else:
            raise ValueError(
                f"Invalid template: {template!r}. Only a single block placeholder is"
                " allowed in a string and no surrounding text is allowed."
            )

    return template

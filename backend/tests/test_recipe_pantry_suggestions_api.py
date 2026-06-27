from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient


REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
INGREDIENTS_URL = "/api/v1/ingredients"
PANTRY_URL = "/api/v1/pantry"
RECIPES_URL = "/api/v1/recipes"
SUGGESTIONS_URL = f"{RECIPES_URL}/suggestions/from-pantry"


async def create_authenticated_user(
    client: AsyncClient,
    *,
    email: str | None = None,
    password: str = "Mealio-password-123",
) -> tuple[dict, dict[str, str]]:
    if email is None:
        email = f"recipe-suggestion-user-{uuid4()}@example.com"

    register_response = await client.post(
        REGISTER_URL,
        json={
            "email": email,
            "full_name": "Recipe Suggestion User",
            "password": password,
        },
    )

    assert register_response.status_code == 201

    login_response = await client.post(
        LOGIN_URL,
        json={
            "email": email,
            "password": password,
        },
    )

    assert login_response.status_code == 200

    access_token = login_response.json()["access_token"]

    return register_response.json(), {
        "Authorization": f"Bearer {access_token}",
    }


async def create_test_ingredient(
    client: AsyncClient,
    *,
    name: str,
    category: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    if headers is None:
        _, headers = await create_authenticated_user(client)

    response = await client.post(
        INGREDIENTS_URL,
        headers=headers,
        json={
            "name": name,
            "category": category,
            "nutrition_value": {
                "calories": "100",
                "protein_g": "10",
                "carbs_g": "5",
                "fat_g": "2",
                "portion_g": "100",
            },
        },
    )

    assert response.status_code == 201

    return response.json()


async def create_test_recipe(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    title: str,
    ingredients: list[dict[str, str]],
    diet_type: str | None = "balanced",
) -> dict:
    payload = {
        "title": title,
        "instructions": "Cook and serve.",
        "ingredients": ingredients,
    }

    if diet_type is not None:
        payload["diet_type"] = diet_type

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json=payload,
    )

    assert response.status_code == 201

    return response.json()


async def add_pantry_item(
    client: AsyncClient,
    *,
    headers: dict[str, str],
    ingredient_id: str,
    quantity_g: str,
) -> dict:
    response = await client.post(
        PANTRY_URL,
        headers=headers,
        json={
            "ingredient_id": ingredient_id,
            "quantity_g": quantity_g,
        },
    )

    assert response.status_code == 201

    return response.json()


def decimal_value(value) -> Decimal:
    return Decimal(str(value))


def get_suggestion_by_recipe_id(
    data: list[dict],
    recipe_id: str,
) -> dict:
    for suggestion in data:
        if suggestion["recipe_id"] == recipe_id:
            return suggestion

    raise AssertionError(f"Recipe {recipe_id} not found in suggestions")


def get_missing_ingredient_by_id(
    data: list[dict],
    ingredient_id: str,
) -> dict:
    for ingredient in data:
        if ingredient["ingredient_id"] == ingredient_id:
            return ingredient

    raise AssertionError(f"Ingredient {ingredient_id} not found in missing ingredients")


@pytest.mark.asyncio
async def test_get_recipe_suggestions_from_current_user_pantry_success(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Suggestion Chicken {uuid4()}",
        category="meat",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Suggestion Rice {uuid4()}",
        category="grain",
    )

    recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Suggestion Chicken Rice Bowl",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "200",
            },
            {
                "ingredient_id": rice["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="250",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=rice["id"],
        quantity_g="40",
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    suggestion = data[0]

    assert suggestion["recipe_id"] == recipe["id"]
    assert suggestion["recipe_title"] == "Suggestion Chicken Rice Bowl"
    assert suggestion["diet_type"] == "balanced"
    assert decimal_value(suggestion["total_calories"]) == Decimal("300")
    assert decimal_value(suggestion["match_percent"]) == Decimal("50")
    assert suggestion["matched_ingredients_count"] == 1
    assert suggestion["missing_ingredients_count"] == 1
    assert suggestion["total_ingredients_count"] == 2

    missing_rice = get_missing_ingredient_by_id(
        suggestion["missing_ingredients"],
        rice["id"],
    )

    assert missing_rice["ingredient_name"] == rice["name"]
    assert decimal_value(missing_rice["required_quantity_g"]) == Decimal("100")
    assert decimal_value(missing_rice["pantry_quantity_g"]) == Decimal("40")
    assert decimal_value(missing_rice["missing_quantity_g"]) == Decimal("60")


@pytest.mark.asyncio
async def test_recipe_suggestion_with_all_ingredients_available_has_100_match(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Full Match Chicken {uuid4()}",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Full Match Rice {uuid4()}",
    )

    await create_test_recipe(
        client,
        headers=headers,
        title="Full Match Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "200",
            },
            {
                "ingredient_id": rice["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="200",
    )
    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=rice["id"],
        quantity_g="500",
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert decimal_value(data[0]["match_percent"]) == Decimal("100")
    assert data[0]["matched_ingredients_count"] == 2
    assert data[0]["missing_ingredients_count"] == 0
    assert data[0]["missing_ingredients"] == []


@pytest.mark.asyncio
async def test_recipe_suggestion_partially_missing_ingredient_returns_difference(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    rice = await create_test_ingredient(
        client,
        name=f"Partial Missing Rice {uuid4()}",
    )

    await create_test_recipe(
        client,
        headers=headers,
        title="Partial Missing Recipe",
        ingredients=[
            {
                "ingredient_id": rice["id"],
                "quantity_g": "200",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=rice["id"],
        quantity_g="50",
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()
    missing_rice = get_missing_ingredient_by_id(
        data[0]["missing_ingredients"],
        rice["id"],
    )

    assert decimal_value(missing_rice["required_quantity_g"]) == Decimal("200")
    assert decimal_value(missing_rice["pantry_quantity_g"]) == Decimal("50")
    assert decimal_value(missing_rice["missing_quantity_g"]) == Decimal("150")


@pytest.mark.asyncio
async def test_recipe_suggestion_ingredient_not_in_pantry_returns_full_missing_quantity(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    oats = await create_test_ingredient(
        client,
        name=f"Not In Pantry Oats {uuid4()}",
    )

    await create_test_recipe(
        client,
        headers=headers,
        title="Not In Pantry Recipe",
        ingredients=[
            {
                "ingredient_id": oats["id"],
                "quantity_g": "80",
            },
        ],
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()
    missing_oats = get_missing_ingredient_by_id(
        data[0]["missing_ingredients"],
        oats["id"],
    )

    assert decimal_value(missing_oats["required_quantity_g"]) == Decimal("80")
    assert decimal_value(missing_oats["pantry_quantity_g"]) == Decimal("0")
    assert decimal_value(missing_oats["missing_quantity_g"]) == Decimal("80")


@pytest.mark.asyncio
async def test_recipe_suggestions_are_sorted_by_best_match_first(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Sorted Chicken {uuid4()}",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Sorted Rice {uuid4()}",
    )
    oil = await create_test_ingredient(
        client,
        name=f"Sorted Oil {uuid4()}",
    )

    await create_test_recipe(
        client,
        headers=headers,
        title="Second Partial Match Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
            {
                "ingredient_id": rice["id"],
                "quantity_g": "100",
            },
        ],
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="First Full Match Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
        ],
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Third Missing Match Recipe",
        ingredients=[
            {
                "ingredient_id": oil["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="100",
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert [item["recipe_title"] for item in data] == [
        "First Full Match Recipe",
        "Second Partial Match Recipe",
        "Third Missing Match Recipe",
    ]


@pytest.mark.asyncio
async def test_recipe_suggestions_limit_and_offset_work(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Pagination Chicken {uuid4()}",
    )

    await create_test_recipe(
        client,
        headers=headers,
        title="Alpha Pagination Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
        ],
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Bravo Pagination Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
        ],
    )
    await create_test_recipe(
        client,
        headers=headers,
        title="Charlie Pagination Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="100",
    )

    response = await client.get(
        SUGGESTIONS_URL,
        headers=headers,
        params={
            "limit": "1",
            "offset": "1",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["recipe_title"] == "Bravo Pagination Recipe"


@pytest.mark.asyncio
async def test_recipe_suggestions_diet_type_filter_works(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    egg = await create_test_ingredient(
        client,
        name=f"Diet Filter Egg {uuid4()}",
    )

    balanced_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Balanced Diet Recipe",
        diet_type="balanced",
        ingredients=[
            {
                "ingredient_id": egg["id"],
                "quantity_g": "100",
            },
        ],
    )
    keto_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Keto Diet Recipe",
        diet_type="keto",
        ingredients=[
            {
                "ingredient_id": egg["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=egg["id"],
        quantity_g="100",
    )

    response = await client.get(
        SUGGESTIONS_URL,
        headers=headers,
        params={
            "diet_type": "keto",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["recipe_id"] == keto_recipe["id"]
    assert data[0]["recipe_id"] != balanced_recipe["id"]


@pytest.mark.asyncio
async def test_recipe_suggestions_min_match_percent_filter_works(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Min Match Chicken {uuid4()}",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Min Match Rice {uuid4()}",
    )

    full_match_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Min Match Full Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
        ],
    )
    low_match_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Min Match Low Recipe",
        ingredients=[
            {
                "ingredient_id": rice["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="100",
    )

    response = await client.get(
        SUGGESTIONS_URL,
        headers=headers,
        params={
            "min_match_percent": "50",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["recipe_id"] == full_match_recipe["id"]
    assert data[0]["recipe_id"] != low_match_recipe["id"]


@pytest.mark.asyncio
async def test_recipe_suggestions_max_missing_ingredients_filter_works(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Max Missing Chicken {uuid4()}",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Max Missing Rice {uuid4()}",
    )
    oil = await create_test_ingredient(
        client,
        name=f"Max Missing Oil {uuid4()}",
    )

    one_missing_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="One Missing Ingredient Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
            {
                "ingredient_id": rice["id"],
                "quantity_g": "100",
            },
        ],
    )
    two_missing_recipe = await create_test_recipe(
        client,
        headers=headers,
        title="Two Missing Ingredients Recipe",
        ingredients=[
            {
                "ingredient_id": rice["id"],
                "quantity_g": "100",
            },
            {
                "ingredient_id": oil["id"],
                "quantity_g": "100",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=headers,
        ingredient_id=chicken["id"],
        quantity_g="100",
    )

    response = await client.get(
        SUGGESTIONS_URL,
        headers=headers,
        params={
            "max_missing_ingredients": "1",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["recipe_id"] == one_missing_recipe["id"]
    assert data[0]["recipe_id"] != two_missing_recipe["id"]


@pytest.mark.asyncio
async def test_recipe_suggestions_empty_pantry_returns_missing_ingredients(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    chicken = await create_test_ingredient(
        client,
        name=f"Empty Pantry Chicken {uuid4()}",
    )
    rice = await create_test_ingredient(
        client,
        name=f"Empty Pantry Rice {uuid4()}",
    )

    await create_test_recipe(
        client,
        headers=headers,
        title="Empty Pantry Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "200",
            },
            {
                "ingredient_id": rice["id"],
                "quantity_g": "100",
            },
        ],
    )

    response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert decimal_value(data[0]["match_percent"]) == Decimal("0")
    assert data[0]["matched_ingredients_count"] == 0
    assert data[0]["missing_ingredients_count"] == 2
    assert len(data[0]["missing_ingredients"]) == 2


@pytest.mark.asyncio
async def test_recipe_suggestions_current_user_sees_only_own_recipes(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-suggestions-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-suggestions-user-{uuid4()}@example.com",
    )

    chicken = await create_test_ingredient(
        client,
        name=f"Private Recipe Chicken {uuid4()}",
    )

    first_recipe = await create_test_recipe(
        client,
        headers=first_headers,
        title="First User Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
        ],
    )
    second_recipe = await create_test_recipe(
        client,
        headers=second_headers,
        title="Second User Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "100",
            },
        ],
    )

    response = await client.get(SUGGESTIONS_URL, headers=first_headers)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["recipe_id"] == first_recipe["id"]
    assert data[0]["recipe_id"] != second_recipe["id"]


@pytest.mark.asyncio
async def test_recipe_suggestions_do_not_use_another_users_pantry(
    client: AsyncClient,
) -> None:
    _, first_headers = await create_authenticated_user(
        client,
        email=f"first-pantry-suggestions-user-{uuid4()}@example.com",
    )
    _, second_headers = await create_authenticated_user(
        client,
        email=f"second-pantry-suggestions-user-{uuid4()}@example.com",
    )

    chicken = await create_test_ingredient(
        client,
        name=f"Private Pantry Chicken {uuid4()}",
    )

    await create_test_recipe(
        client,
        headers=first_headers,
        title="First User Pantry Isolation Recipe",
        ingredients=[
            {
                "ingredient_id": chicken["id"],
                "quantity_g": "500",
            },
        ],
    )

    await add_pantry_item(
        client,
        headers=second_headers,
        ingredient_id=chicken["id"],
        quantity_g="500",
    )

    response = await client.get(SUGGESTIONS_URL, headers=first_headers)

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1

    missing_chicken = get_missing_ingredient_by_id(
        data[0]["missing_ingredients"],
        chicken["id"],
    )

    assert decimal_value(data[0]["match_percent"]) == Decimal("0")
    assert decimal_value(missing_chicken["pantry_quantity_g"]) == Decimal("0")
    assert decimal_value(missing_chicken["missing_quantity_g"]) == Decimal("500")


@pytest.mark.asyncio
async def test_recipe_suggestions_require_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get(SUGGESTIONS_URL)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_recipe_suggestions_reject_invalid_token(
    client: AsyncClient,
) -> None:
    response = await client.get(
        SUGGESTIONS_URL,
        headers={
            "Authorization": "Bearer invalid-token",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_recipe_suggestions_reject_invalid_limit(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        SUGGESTIONS_URL,
        headers=headers,
        params={
            "limit": "0",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recipe_suggestions_reject_invalid_offset(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        SUGGESTIONS_URL,
        headers=headers,
        params={
            "offset": "-1",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recipe_suggestions_reject_invalid_min_match_percent(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        SUGGESTIONS_URL,
        headers=headers,
        params={
            "min_match_percent": "101",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recipe_suggestions_reject_invalid_max_missing_ingredients(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.get(
        SUGGESTIONS_URL,
        headers=headers,
        params={
            "max_missing_ingredients": "-1",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_recipe_suggestions_skip_recipes_without_ingredients(
    client: AsyncClient,
) -> None:
    _, headers = await create_authenticated_user(client)

    response = await client.post(
        RECIPES_URL,
        headers=headers,
        json={
            "title": "Recipe Without Ingredients",
            "instructions": "No ingredients.",
            "diet_type": "balanced",
            "ingredients": [],
        },
    )

    assert response.status_code == 201

    suggestions_response = await client.get(SUGGESTIONS_URL, headers=headers)

    assert suggestions_response.status_code == 200
    assert suggestions_response.json() == []

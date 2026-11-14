import 'dart:async';

import 'package:dio/dio.dart';
import 'package:mealio/features/recipes/data/recipe_repository.dart';
import 'package:mealio/features/recipes/domain/recipe.dart';
import 'package:mealio/features/recipes/domain/recipe_detail.dart';

Map<String, dynamic> recipeJson({
  String id = 'recipe-1',
  String title = 'Saved recipe',
}) => {
  'id': id,
  'created_by_user_id': 'owner-1',
  'title': title,
  'description': 'A saved recipe description',
  'instructions': 'First step.\nSecond step.',
  'servings': 4,
  'meal_type': 'brunch',
  'prep_time_minutes': 30,
  'diet_type': null,
  'total_calories': '330.00',
  'total_protein_g': '62.00',
  'total_carbs_g': '0.00',
  'total_fat_g': '7.20',
  'created_at': '2026-11-14T10:00:00Z',
  'updated_at': '2026-11-14T10:00:00Z',
  'recipe_ingredients': [
    <String, dynamic>{
      'id': 'composition-1',
      'recipe_id': id,
      'ingredient_id': 'ingredient-1',
      'quantity_g': '200.00',
    },
  ],
};

List<Recipe> recipePage({int start = 0, int count = 50}) => [
  for (var i = start; i < start + count; i++)
    Recipe.fromJson(recipeJson(id: 'recipe-$i', title: 'Saved recipe $i')),
];

typedef RecipeRequest = ({int lifetime, int limit, int offset});
typedef RecipeDetailRequest = ({
  String recipeId,
  int lifetime,
  CancelToken? cancelToken,
});

Map<String, dynamic> recipeIngredientJson({
  String id = 'ingredient-1',
  String name = 'Named ingredient',
}) => {
  'id': id,
  'name': name,
  'category': null,
  'created_at': '2026-11-14T10:00:00Z',
  'nutrition_value': null,
};

RecipeDetail recipeDetailFixture({
  String id = 'recipe-1',
  String title = 'Saved recipe',
}) => RecipeDetail(
  recipe: Recipe.fromJson(recipeJson(id: id, title: title)),
  ingredientNames: {'ingredient-1': 'Named ingredient'},
);

class FakeRecipeRepository implements RecipeRepository {
  FakeRecipeRepository([this.handler]);

  FutureOr<List<Recipe>> Function(RecipeRequest)? handler;
  final calls = <RecipeRequest>[];
  FutureOr<RecipeDetail> Function(RecipeDetailRequest)? detailHandler;
  final detailCalls = <RecipeDetailRequest>[];

  @override
  Future<RecipeDetail> getRecipeDetail({
    required String recipeId,
    required int lifetime,
    CancelToken? cancelToken,
  }) async {
    final request = (
      recipeId: recipeId,
      lifetime: lifetime,
      cancelToken: cancelToken,
    );
    detailCalls.add(request);
    return await detailHandler?.call(request) ??
        recipeDetailFixture(id: recipeId);
  }

  @override
  Future<List<Recipe>> getRecipes({
    required int lifetime,
    required int limit,
    required int offset,
  }) async {
    final request = (lifetime: lifetime, limit: limit, offset: offset);
    calls.add(request);
    return await handler?.call(request) ?? [];
  }
}

import 'recipe.dart';

/// Published only after every composition reference has a readable name.
class RecipeDetail {
  RecipeDetail({
    required this.recipe,
    required Map<String, String> ingredientNames,
  }) : ingredientNames = Map.unmodifiable(ingredientNames) {
    for (final item in recipe.ingredients) {
      if (this.ingredientNames[item.ingredientId]?.trim().isNotEmpty != true) {
        throw const FormatException('Incomplete recipe composition');
      }
    }
  }

  final Recipe recipe;
  final Map<String, String> ingredientNames;
}

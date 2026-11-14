import 'package:flutter/material.dart';

import '../../../core/localization/l10n.dart';
import '../domain/recipe.dart';
import 'recipe_localization.dart';

/// The same whole-recipe totals and missing/zero semantics on list and detail.
class RecipeNutritionSummary extends StatelessWidget {
  const RecipeNutritionSummary({super.key, required this.recipe});

  final Recipe recipe;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    String value(double? amount) => amount == null
        ? l10n.recipeNoNutrition
        : formatRecipeNumber(context, amount);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(l10n.recipeServings(recipe.servings)),
        const SizedBox(height: 12),
        Text(
          l10n.recipeWholeNutrition,
          style: Theme.of(context).textTheme.titleSmall,
        ),
        Text(l10n.recipeCalories(value(recipe.totalCalories))),
        Text(l10n.recipeProtein(value(recipe.totalProteinG))),
        Text(l10n.recipeCarbs(value(recipe.totalCarbsG))),
        Text(l10n.recipeFat(value(recipe.totalFatG))),
      ],
    );
  }
}

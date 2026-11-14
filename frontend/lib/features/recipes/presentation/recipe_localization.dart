import 'package:flutter/widgets.dart';
import 'package:intl/intl.dart';

import '../../../l10n/generated/app_localizations.dart';
import '../domain/recipe_failure.dart';

extension LocalizedRecipeFailure on RecipeFailure {
  String localized(AppLocalizations l10n, {bool detail = false}) =>
      switch (type) {
        RecipeFailureType.connection => l10n.connectionError,
        RecipeFailureType.authentication => l10n.recipesAuthentication,
        RecipeFailureType.rateLimited => l10n.rateLimited,
        RecipeFailureType.unexpected =>
          detail ? l10n.recipeDetailLoadError : l10n.recipesLoadError,
        RecipeFailureType.unavailable => l10n.recipeUnavailable,
        RecipeFailureType.ingredientUnavailable =>
          l10n.recipeIngredientUnavailable,
      };
}

String formatRecipeNumber(BuildContext context, double value) =>
    (NumberFormat.decimalPattern(Localizations.localeOf(context).toString())
          ..minimumFractionDigits = 0
          ..maximumFractionDigits = 2)
        .format(value);

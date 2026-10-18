import '../../../l10n/generated/app_localizations.dart';
import '../domain/nutrition_failure.dart';
import '../domain/nutrition_profile.dart';
import '../domain/nutrition_preferences.dart';
import '../domain/nutrition_calculation.dart';

String nutritionFieldLabel(NutritionField field, AppLocalizations l10n) =>
    switch (field) {
      NutritionField.goal => l10n.nutritionGoal,
      NutritionField.sex => l10n.nutritionSex,
      NutritionField.birthDate => l10n.nutritionBirthDate,
      NutritionField.height => l10n.nutritionHeight,
      NutritionField.weight => l10n.nutritionWeight,
      NutritionField.activity => l10n.nutritionActivity,
    };

String nutritionChoiceLabel(String value, AppLocalizations l10n) =>
    switch (value) {
      'lose_weight' => l10n.nutritionLose,
      'maintain' => l10n.nutritionMaintain,
      'gain_weight' => l10n.nutritionGain,
      'male' => l10n.nutritionMale,
      'female' => l10n.nutritionFemale,
      'sedentary' => l10n.nutritionSedentary,
      'lightly_active' => l10n.nutritionLightlyActive,
      'moderately_active' => l10n.nutritionModeratelyActive,
      'very_active' => l10n.nutritionVeryActive,
      'extra_active' => l10n.nutritionExtraActive,
      _ => l10n.nutritionChoose,
    };

String? nutritionErrorLabel(
  NutritionInputError? error,
  AppLocalizations l10n,
) => switch (error) {
  null => null,
  NutritionInputError.required => l10n.nutritionRequired,
  NutritionInputError.choice => l10n.nutritionChoose,
  NutritionInputError.birthDate => l10n.nutritionDateInvalid,
  NutritionInputError.height => l10n.nutritionHeightInvalid,
  NutritionInputError.weight => l10n.nutritionWeightInvalid,
};

String nutritionFailureLabel(NutritionFailure failure, AppLocalizations l10n) =>
    switch (failure.type) {
      NutritionFailureType.authentication => l10n.nutritionAuthentication,
      NutritionFailureType.validation => l10n.nutritionValidation,
      NutritionFailureType.rateLimited => l10n.rateLimited,
      NutritionFailureType.connection => l10n.nutritionConnection,
      NutritionFailureType.unexpected => l10n.nutritionUnexpected,
    };

String preferenceFieldLabel(PreferenceField field, AppLocalizations l10n) =>
    switch (field) {
      PreferenceField.diet => l10n.nutritionDiet,
      PreferenceField.cookingTime => l10n.nutritionCookingTime,
      PreferenceField.budgetAmount => l10n.nutritionBudget,
      PreferenceField.currency => l10n.nutritionCurrency,
    };
String preferenceListLabel(PreferenceList field, AppLocalizations l10n) =>
    switch (field) {
      PreferenceList.allergies => l10n.nutritionAllergies,
      PreferenceList.likes => l10n.nutritionLikes,
      PreferenceList.dislikes => l10n.nutritionDislikes,
    };
String? preferenceErrorLabel(PreferenceError? error, AppLocalizations l10n) =>
    switch (error) {
      null => null,
      PreferenceError.diet => l10n.nutritionDietInvalid,
      PreferenceError.cookingTime => l10n.nutritionCookingInvalid,
      PreferenceError.budgetAmount => l10n.nutritionBudgetInvalid,
      PreferenceError.currency => l10n.nutritionCurrencyInvalid,
      PreferenceError.budgetPair => l10n.nutritionBudgetPair,
    };
String nutritionReasonLabel(
  NutritionUnsupportedReason reason,
  AppLocalizations l10n,
) => switch (reason) {
  NutritionUnsupportedReason.birthDateAfterCalculationDate =>
    l10n.nutritionReasonBirthDate,
  NutritionUnsupportedReason.age => l10n.nutritionReasonAge,
  NutritionUnsupportedReason.height => l10n.nutritionReasonHeight,
  NutritionUnsupportedReason.weight => l10n.nutritionReasonWeight,
  NutritionUnsupportedReason.bmi => l10n.nutritionReasonBmi,
  NutritionUnsupportedReason.energy => l10n.nutritionReasonEnergy,
  NutritionUnsupportedReason.calories => l10n.nutritionReasonCalories,
};

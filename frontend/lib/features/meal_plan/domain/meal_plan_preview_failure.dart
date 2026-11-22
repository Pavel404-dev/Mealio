enum MealPlanPreviewFailureType {
  authentication,
  noEligibleRecipes,
  inProgress,
  inputsChanged,
  rateLimited,
  providerUnavailable,
  connection,
  unexpected,
}

class MealPlanPreviewFailure implements Exception {
  const MealPlanPreviewFailure(this.type);

  final MealPlanPreviewFailureType type;
}

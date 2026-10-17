enum NutritionFailureType {
  authentication,
  validation,
  rateLimited,
  connection,
  unexpected,
}

class NutritionFailure implements Exception {
  const NutritionFailure(this.type);
  final NutritionFailureType type;
}

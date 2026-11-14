enum RecipeFailureType {
  connection,
  authentication,
  rateLimited,
  unexpected,
  unavailable,
  ingredientUnavailable,
}

/// Never contains server response text or credentials.
class RecipeFailure implements Exception {
  const RecipeFailure(this.type);

  final RecipeFailureType type;
}

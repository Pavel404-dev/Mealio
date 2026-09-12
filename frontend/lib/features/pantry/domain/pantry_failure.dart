enum PantryFailureType {
  connection,
  duplicate,
  ingredientUnavailable,
  validation,
  authentication,
  backend,
  unexpected,
}

class PantryFailure implements Exception {
  const PantryFailure({required this.type, required this.message});

  factory PantryFailure.connection() {
    return const PantryFailure(
      type: PantryFailureType.connection,
      message: 'Unable to connect to the server. Please try again.',
    );
  }

  factory PantryFailure.backend() {
    return const PantryFailure(
      type: PantryFailureType.backend,
      message: 'Unable to load your pantry. Please try again.',
    );
  }

  factory PantryFailure.searchBackend() {
    return const PantryFailure(
      type: PantryFailureType.backend,
      message: 'Unable to load ingredients. Please try again.',
    );
  }

  factory PantryFailure.createBackend() {
    return const PantryFailure(
      type: PantryFailureType.backend,
      message: 'Unable to add this ingredient. Please try again.',
    );
  }

  factory PantryFailure.duplicate() {
    return const PantryFailure(
      type: PantryFailureType.duplicate,
      message: 'This ingredient is already in your pantry.',
    );
  }

  factory PantryFailure.ingredientUnavailable() {
    return const PantryFailure(
      type: PantryFailureType.ingredientUnavailable,
      message: 'This ingredient is no longer available.',
    );
  }

  factory PantryFailure.validation() {
    return const PantryFailure(
      type: PantryFailureType.validation,
      message: 'Check the entered values and try again.',
    );
  }

  factory PantryFailure.authentication() {
    return const PantryFailure(
      type: PantryFailureType.authentication,
      message: 'Your session is no longer valid. Please sign in again.',
    );
  }

  factory PantryFailure.searchUnexpected() {
    return const PantryFailure(
      type: PantryFailureType.unexpected,
      message: 'Unable to load ingredients. Please try again.',
    );
  }

  factory PantryFailure.createUnexpected() {
    return const PantryFailure(
      type: PantryFailureType.unexpected,
      message: 'Unable to add this ingredient. Please try again.',
    );
  }

  factory PantryFailure.unexpected() {
    return const PantryFailure(
      type: PantryFailureType.unexpected,
      message: 'Unable to load your pantry. Please try again.',
    );
  }

  final PantryFailureType type;
  final String message;

  @override
  String toString() => 'PantryFailure($type)';
}

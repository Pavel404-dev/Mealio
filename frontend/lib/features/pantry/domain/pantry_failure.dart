enum PantryFailureType { connection, backend, unexpected }

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

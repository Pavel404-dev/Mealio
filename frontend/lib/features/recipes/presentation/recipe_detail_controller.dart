import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../../../core/storage/secure_storage_provider.dart';
import '../data/recipe_repository.dart';
import '../domain/recipe_detail.dart';
import '../domain/recipe_failure.dart';

/// One recipe ID in one login lifetime. Cancels both the initial GET and any
/// pending ingredient lookups when the visit is retired.
class RecipeDetailController extends ChangeNotifier {
  RecipeDetailController({
    required String recipeId,
    required RecipeRepository repository,
    required SecureStorageService storage,
    required bool Function() isAuthenticated,
  }) : this._(
         recipeId,
         repository,
         storage,
         isAuthenticated,
         storage.sessionLifetime,
       );

  RecipeDetailController._(
    this.recipeId,
    this._repository,
    this._storage,
    this._isAuthenticated,
    this.lifetime,
  );

  final String recipeId;
  final RecipeRepository _repository;
  final SecureStorageService _storage;
  final bool Function() _isAuthenticated;
  final int lifetime;
  bool _active = true;
  bool _disposed = false;
  CancelToken? _request;

  bool loading = false;
  RecipeDetail? detail;
  RecipeFailure? failure;

  bool get isCurrent =>
      !_disposed &&
      _active &&
      _storage.ownsSession(lifetime) &&
      _isAuthenticated();

  bool checkOwnership() {
    if (isCurrent) return true;
    if (!_disposed && _active) {
      _active = false;
      _clear();
      notifyListeners();
    }
    return false;
  }

  Future<void> load() async {
    if (!checkOwnership() || loading || detail != null) return;
    final request = _request = CancelToken();
    loading = true;
    failure = null;
    notifyListeners();
    try {
      final result = await _repository.getRecipeDetail(
        recipeId: recipeId,
        lifetime: lifetime,
        cancelToken: request,
      );
      if (!checkOwnership()) return;
      detail = result;
      loading = false;
      notifyListeners();
    } catch (error) {
      if (!checkOwnership()) return;
      loading = false;
      failure = error is RecipeFailure
          ? error
          : const RecipeFailure(RecipeFailureType.unexpected);
      notifyListeners();
    } finally {
      if (identical(_request, request)) _request = null;
    }
  }

  void _clear() {
    _request?.cancel();
    _request = null;
    loading = false;
    detail = null;
    failure = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _clear();
    super.dispose();
  }
}

import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../../../core/storage/secure_storage_provider.dart';
import '../../recipes/data/recipe_repository.dart';
import '../../recipes/domain/recipe_failure.dart';
import '../data/meal_plan_preview_repository.dart';
import '../domain/meal_plan_preview.dart';
import '../domain/meal_plan_preview_failure.dart';

class MealPlanPreviewController extends ChangeNotifier {
  MealPlanPreviewController({
    required MealPlanPreviewRepository repository,
    required RecipeRepository recipes,
    required SecureStorageService storage,
    required bool Function() isAuthenticated,
  }) : this._(
         repository,
         recipes,
         storage,
         isAuthenticated,
         storage.sessionLifetime,
       );

  MealPlanPreviewController._(
    this._repository,
    this._recipes,
    this._storage,
    this._isAuthenticated,
    this._lifetime,
  );

  final MealPlanPreviewRepository _repository;
  final RecipeRepository _recipes;
  final SecureStorageService _storage;
  final bool Function() _isAuthenticated;
  final int _lifetime;
  bool _active = true;
  bool _disposed = false;
  CancelToken? _cancelToken;
  MealPlanPreviewRequest? _lastRequest;
  String? _lastKey;

  bool loading = false;
  MealPlanPreview? preview;
  MealPlanPreviewFailure? failure;
  Map<String, String> recipeTitles = const {};

  bool get isCurrent =>
      !_disposed &&
      _active &&
      _storage.ownsSession(_lifetime) &&
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

  Future<void> generate(MealPlanPreviewRequest request) =>
      _generate(request, _newKey());

  Future<void> retry() async {
    final request = _lastRequest;
    final key = _lastKey;
    final error = failure;
    if (request == null || key == null || error == null) return;
    await _generate(
      request,
      error.type == MealPlanPreviewFailureType.inputsChanged ? _newKey() : key,
    );
  }

  void reset() {
    if (!checkOwnership() || loading) return;
    _clear();
    notifyListeners();
  }

  Future<void> _generate(MealPlanPreviewRequest request, String key) async {
    if (!checkOwnership() || loading) return;
    _lastRequest = request;
    _lastKey = key;
    final cancelToken = _cancelToken = CancelToken();
    loading = true;
    preview = null;
    failure = null;
    recipeTitles = const {};
    notifyListeners();
    try {
      final result = await _repository.generate(
        request: request,
        idempotencyKey: key,
        lifetime: _lifetime,
        cancelToken: cancelToken,
      );
      if (!checkOwnership()) return;
      final recipeIds = result.items.map((item) => item.recipeId).toSet();
      final titles = await Future.wait(
        recipeIds.map((id) async {
          try {
            final recipe = await _recipes.getRecipe(
              recipeId: id,
              lifetime: _lifetime,
              cancelToken: cancelToken,
            );
            return MapEntry(recipe.id, recipe.title);
          } on RecipeFailure {
            return null;
          }
        }),
      );
      if (!checkOwnership()) return;
      recipeTitles = Map.unmodifiable(
        Map.fromEntries(titles.whereType<MapEntry<String, String>>()),
      );
      preview = result;
    } catch (error) {
      if (!checkOwnership()) return;
      failure = error is MealPlanPreviewFailure
          ? error
          : const MealPlanPreviewFailure(MealPlanPreviewFailureType.unexpected);
    } finally {
      if (identical(_cancelToken, cancelToken)) _cancelToken = null;
    }
    loading = false;
    notifyListeners();
  }

  void _clear() {
    _cancelToken?.cancel();
    _cancelToken = null;
    loading = false;
    preview = null;
    failure = null;
    recipeTitles = const {};
    _lastRequest = null;
    _lastKey = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _clear();
    super.dispose();
  }
}

String _newKey() {
  final random = Random.secure();
  return List.generate(
    16,
    (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
  ).join();
}

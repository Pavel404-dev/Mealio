import 'package:flutter/foundation.dart';

import '../../../core/storage/secure_storage_provider.dart';
import '../data/recipe_repository.dart';
import '../domain/recipe.dart';
import '../domain/recipe_failure.dart';

/// One route visit in one login lifetime, like NutritionSetupController.
class RecipeListController extends ChangeNotifier {
  RecipeListController({
    required RecipeRepository repository,
    required SecureStorageService storage,
    required bool Function() isAuthenticated,
  }) : this._(repository, storage, isAuthenticated, storage.sessionLifetime);

  RecipeListController._(
    this._repository,
    this._storage,
    this._isAuthenticated,
    this.lifetime,
  );

  static const pageSize = 50;
  final RecipeRepository _repository;
  final SecureStorageService _storage;
  final bool Function() _isAuthenticated;
  final int lifetime;
  bool _active = true;
  bool _disposed = false;
  int _nextOffset = 0;
  List<Recipe> _items = const [];

  List<Recipe> get items => _items;
  bool loaded = false;
  bool loading = false;
  bool hasMore = false;
  RecipeFailure? failure;

  bool get isCurrent =>
      !_disposed &&
      _active &&
      _storage.ownsSession(lifetime) &&
      _isAuthenticated();

  /// Auth transitions call this even when no request is pending. The storage
  /// provider itself is stable and does not notify on lifetime changes.
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
    if (!loaded) await _loadPage();
  }

  Future<void> loadMore() async {
    if (loaded && hasMore) await _loadPage();
  }

  Future<void> retry() => loaded ? loadMore() : load();

  Future<void> _loadPage() async {
    if (!checkOwnership() || loading) return;
    loading = true;
    failure = null;
    notifyListeners();
    try {
      final page = await _repository.getRecipes(
        lifetime: lifetime,
        limit: pageSize,
        offset: _nextOffset,
      );
      if (!checkOwnership()) return;
      // Offset counts server rows, including repeats from a changing collection.
      // Deduplication must not move the next request backwards.
      final byId = {for (final item in _items) item.id: item};
      for (final item in page) {
        byId[item.id] = item;
      }
      _items = List.unmodifiable(byId.values);
      _nextOffset += page.length;
      hasMore = page.length == pageSize;
      loaded = true;
      loading = false;
      notifyListeners();
    } catch (error) {
      if (!checkOwnership()) return;
      loading = false;
      failure = error is RecipeFailure
          ? error
          : const RecipeFailure(RecipeFailureType.unexpected);
      notifyListeners();
    }
  }

  void _clear() {
    _items = const [];
    _nextOffset = 0;
    loaded = false;
    loading = false;
    hasMore = false;
    failure = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _clear();
    super.dispose();
  }
}

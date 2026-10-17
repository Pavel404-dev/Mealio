import 'package:flutter/foundation.dart';

import '../../../core/storage/secure_storage_provider.dart';
import '../data/nutrition_repository.dart';
import '../domain/nutrition_failure.dart';
import '../domain/nutrition_profile.dart';

enum NutritionSaveResult { advanced, finished, rejected, stale }

/// One route visit in one login lifetime. Never persisted or rebound to a login.
class NutritionSetupController extends ChangeNotifier {
  NutritionSetupController({
    required NutritionRepository repository,
    required SecureStorageService storage,
    required bool Function() isAuthenticated,
  }) : this._(repository, storage, isAuthenticated, storage.sessionLifetime);

  NutritionSetupController._(
    this._repository,
    this._storage,
    this._isAuthenticated,
    this.lifetime,
  );

  final NutritionRepository _repository;
  final SecureStorageService _storage;
  final bool Function() _isAuthenticated;
  final int lifetime;
  bool _active = true;
  bool _disposed = false;
  final _saved = <NutritionField, String?>{};
  final _input = <NutritionField, String>{};
  final _errors = <NutritionField, NutritionInputError>{};

  int step = 0;
  bool loading = false;
  bool loaded = false;
  bool saving = false;
  bool? lastSaveWrote;
  NutritionFailure? failure;

  String input(NutritionField field) => _input[field] ?? '';
  NutritionInputError? error(NutritionField field) => _errors[field];
  bool get isCurrent =>
      !_disposed &&
      _active &&
      _storage.ownsSession(lifetime) &&
      _isAuthenticated();
  bool get dirty =>
      loaded &&
      NutritionField.values.any(
        (field) => !nutritionValuesEqual(field, input(field), _saved[field]),
      );

  /// Called on auth transitions as well as before and after async work. Merely
  /// watching the stable storage provider would not observe lifetime changes.
  bool checkOwnership() {
    if (isCurrent) return true;
    if (_active && !_disposed) {
      _active = false;
      _clear();
      notifyListeners();
    }
    return false;
  }

  Future<void> load() async {
    if (!checkOwnership() || loading || loaded) return;
    loading = true;
    failure = null;
    notifyListeners();
    try {
      if (!checkOwnership()) return;
      final profile = await _repository.load(lifetime: lifetime);
      if (!checkOwnership()) return;
      _saved.addAll(profile.values);
      _input.addAll(
        profile.values.map((key, value) => MapEntry(key, value ?? '')),
      );
      loaded = true;
      loading = false;
      notifyListeners();
    } catch (error) {
      if (!checkOwnership()) return;
      loading = false;
      failure = _safeFailure(error);
      notifyListeners();
    }
  }

  void edit(NutritionField field, String value) {
    if (!checkOwnership() || !loaded || saving) return;
    _input[field] = value;
    _errors.remove(field);
    failure = null;
    lastSaveWrote = null;
    notifyListeners();
  }

  void back() {
    if (!checkOwnership() || saving || step == 0) return;
    step--;
    _errors.clear();
    failure = null;
    lastSaveWrote = null;
    notifyListeners();
  }

  Future<NutritionSaveResult> save() async {
    if (!checkOwnership()) return NutritionSaveResult.stale;
    if (!loaded || saving) return NutritionSaveResult.rejected;
    final fields = NutritionField.values.where((field) => field.step == step);
    _errors.clear();
    for (final field in fields) {
      final error = nutritionInputError(field, input(field));
      if (error != null) _errors[field] = error;
    }
    if (_errors.isNotEmpty) {
      notifyListeners();
      return NutritionSaveResult.rejected;
    }
    final changes = {
      for (final field in fields)
        if (!nutritionValuesEqual(field, input(field), _saved[field]))
          field: nutritionWireValue(input(field)),
    };
    saving = true;
    failure = null;
    lastSaveWrote = null;
    notifyListeners();
    try {
      if (!checkOwnership()) return NutritionSaveResult.stale;
      if (changes.isNotEmpty) {
        final profile = await _repository.save(
          lifetime: lifetime,
          changes: Map.unmodifiable(changes),
        );
        if (!checkOwnership()) return NutritionSaveResult.stale;
        // Only this step is acknowledged. Other steps keep their input and
        // comparison baseline, including dirty edits made before revisiting.
        for (final field in fields) {
          _saved[field] = profile.values[field];
          _input[field] = profile.values[field] ?? '';
        }
      }
      if (!checkOwnership()) return NutritionSaveResult.stale;
      saving = false;
      lastSaveWrote = changes.isNotEmpty;
      final finished = step == 2;
      if (!finished) step++;
      notifyListeners();
      return finished
          ? NutritionSaveResult.finished
          : NutritionSaveResult.advanced;
    } catch (error) {
      if (!checkOwnership()) return NutritionSaveResult.stale;
      saving = false;
      failure = _safeFailure(error);
      notifyListeners();
      return NutritionSaveResult.rejected;
    }
  }

  NutritionFailure _safeFailure(Object error) => error is NutritionFailure
      ? error
      : const NutritionFailure(NutritionFailureType.unexpected);

  void _clear() {
    _saved.clear();
    _input.clear();
    _errors.clear();
    loaded = loading = saving = false;
    step = 0;
    failure = null;
    lastSaveWrote = null;
  }

  @override
  void dispose() {
    _disposed = true;
    _active = false;
    _clear();
    super.dispose();
  }
}

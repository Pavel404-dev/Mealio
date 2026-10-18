import 'package:flutter/foundation.dart';

import '../../../core/storage/secure_storage_provider.dart';
import '../data/nutrition_repository.dart';
import '../domain/nutrition_failure.dart';
import '../domain/nutrition_profile.dart';
import '../domain/nutrition_preferences.dart';
import '../domain/nutrition_calculation.dart';

enum NutritionSaveResult {
  advanced,
  finishedWithoutWrite,
  targetsApplied,
  rejected,
  stale,
}

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

  static const stepCount = 6;
  final _preferenceInput = <PreferenceField, String>{};
  final _preferenceSaved = <PreferenceField, String>{};
  final _lists = <PreferenceList, List<String>>{};
  final _savedLists = <PreferenceList, List<String>>{};
  final preferenceErrors = <PreferenceField, PreferenceError>{};
  NutritionTargets targets = const NutritionTargets();
  NutritionCalculation? calculation;
  bool calculating = false;
  bool useEstimate = false;
  int _generation = 0;

  String preferenceInput(PreferenceField field) =>
      _preferenceInput[field] ?? '';
  List<String> ingredients(PreferenceList field) =>
      List.unmodifiable(_lists[field] ?? []);
  bool get formulaDirty => NutritionField.values.any(
    (f) => !nutritionValuesEqual(f, input(f), _saved[f]),
  );
  bool _preferenceEqual(PreferenceField field) {
    final input = preferenceInput(field).trim();
    final saved = _preferenceSaved[field] ?? '';
    if (preferenceError(field, input) != null) return false;
    if (field == PreferenceField.budgetAmount &&
        input.isNotEmpty &&
        saved.isNotEmpty) {
      return moneyCents(input) == moneyCents(saved);
    }
    if (field == PreferenceField.currency) return input.toUpperCase() == saved;
    if (field == PreferenceField.cookingTime &&
        input.isNotEmpty &&
        saved.isNotEmpty) {
      return int.parse(input) == int.parse(saved);
    }
    return input == saved;
  }

  bool get preferencesDirty =>
      PreferenceField.values.any((f) => !_preferenceEqual(f)) ||
      PreferenceList.values.any(
        (f) => !ingredientListsEqual(ingredients(f), _savedLists[f] ?? []),
      );

  void editPreference(PreferenceField field, String value) {
    if (!checkOwnership() || !loaded || saving) return;
    _preferenceInput[field] = value;
    preferenceErrors.clear();
    failure = null;
    lastSaveWrote = null;
    notifyListeners();
  }

  void editIngredients(PreferenceList field, List<String> value) {
    if (!checkOwnership() || !loaded || saving) return;
    _lists[field] = List.of(value);
    failure = null;
    lastSaveWrote = null;
    notifyListeners();
  }

  void selectEstimate(bool value) {
    if (!checkOwnership() ||
        saving ||
        calculating ||
        calculation is! NutritionCalculated ||
        formulaDirty) {
      return;
    }
    useEstimate = value;
    notifyListeners();
  }

  void _invalidateCalculation() {
    _generation++;
    calculation = null;
    calculating = false;
    useEstimate = false;
  }

  void _ackPreferences(NutritionPreferences profile, int step) {
    for (final field in PreferenceField.values.where(
      (f) => (f == PreferenceField.diet ? 3 : 4) == step,
    )) {
      _preferenceSaved[field] = _preferenceInput[field] = profile.text(field);
    }
    if (step == 3) {
      for (final field in PreferenceList.values) {
        _savedLists[field] = profile.list(field);
        _lists[field] = List.of(profile.list(field));
      }
    }
  }

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
  bool get dirty => loaded && (formulaDirty || preferencesDirty);

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
      _ackPreferences(profile.preferences, 3);
      _ackPreferences(profile.preferences, 4);
      targets = profile.targets;
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
    if (input(field) != value) _invalidateCalculation();
    _input[field] = value;
    _errors.remove(field);
    failure = null;
    lastSaveWrote = null;
    notifyListeners();
  }

  void back() {
    if (!checkOwnership() || saving || step == 0) return;
    if (calculating) _invalidateCalculation();
    step--;
    _errors.clear();
    failure = null;
    lastSaveWrote = null;
    notifyListeners();
  }

  Future<NutritionSaveResult> save() async {
    if (!checkOwnership()) return NutritionSaveResult.stale;
    if (!loaded || saving) return NutritionSaveResult.rejected;
    if (step == 5) return confirm();
    if (step >= 3) return _savePreferences();
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
          changes: NutritionPatch.formula(changes),
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
      step++;
      notifyListeners();
      return NutritionSaveResult.advanced;
    } catch (error) {
      if (!checkOwnership()) return NutritionSaveResult.stale;
      saving = false;
      failure = _safeFailure(error);
      notifyListeners();
      return NutritionSaveResult.rejected;
    }
  }

  Future<NutritionSaveResult> _savePreferences() async {
    preferenceErrors.clear();
    final fields = PreferenceField.values.where(
      (f) => (f == PreferenceField.diet ? 3 : 4) == step,
    );
    for (final field in fields) {
      final error = preferenceError(field, preferenceInput(field));
      if (error != null) preferenceErrors[field] = error;
    }
    if (step == 4 &&
        preferenceInput(PreferenceField.budgetAmount).trim().isEmpty !=
            preferenceInput(PreferenceField.currency).trim().isEmpty) {
      preferenceErrors[PreferenceField.budgetAmount] =
          PreferenceError.budgetPair;
    }
    if (preferenceErrors.isNotEmpty) {
      notifyListeners();
      return NutritionSaveResult.rejected;
    }
    NutritionChange<List<String>>? listChange(PreferenceList field) =>
        ingredientListsEqual(ingredients(field), _savedLists[field] ?? [])
        ? null
        : NutritionChange(ingredients(field));
    final time = preferenceInput(PreferenceField.cookingTime).trim();
    final amount = preferenceInput(PreferenceField.budgetAmount).trim();
    final patch = step == 3
        ? NutritionPatch.food(
            diet: _preferenceEqual(PreferenceField.diet)
                ? null
                : NutritionChange(preferenceInput(PreferenceField.diet)),
            allergies: listChange(PreferenceList.allergies),
            likes: listChange(PreferenceList.likes),
            dislikes: listChange(PreferenceList.dislikes),
          )
        : NutritionPatch.practical(
            cookingTime: _preferenceEqual(PreferenceField.cookingTime)
                ? null
                : NutritionChange(time.isEmpty ? null : int.parse(time)),
            budget:
                _preferenceEqual(PreferenceField.budgetAmount) &&
                    _preferenceEqual(PreferenceField.currency)
                ? null
                : NutritionChange(
                    amount.isEmpty
                        ? null
                        : NutritionBudget(
                            amount,
                            preferenceInput(PreferenceField.currency),
                          ),
                  ),
          );
    saving = true;
    failure = null;
    lastSaveWrote = null;
    notifyListeners();
    try {
      if (!checkOwnership()) return NutritionSaveResult.stale;
      if (!patch.isEmpty) {
        final profile = await _repository.save(
          lifetime: lifetime,
          changes: patch,
        );
        if (!checkOwnership()) return NutritionSaveResult.stale;
        _ackPreferences(profile.preferences, step);
      }
      if (!checkOwnership()) return NutritionSaveResult.stale;
      saving = false;
      lastSaveWrote = !patch.isEmpty;
      step++;
      notifyListeners();
      return NutritionSaveResult.advanced;
    } catch (error) {
      if (!checkOwnership()) return NutritionSaveResult.stale;
      saving = false;
      failure = _safeFailure(error);
      notifyListeners();
      return NutritionSaveResult.rejected;
    }
  }

  Future<void> calculate({DateTime? now}) async {
    if (!checkOwnership() || !loaded || saving || calculating || step != 5) {
      return;
    }
    if (formulaDirty) {
      failure = const NutritionFailure(NutritionFailureType.validation);
      notifyListeners();
      return;
    }
    _invalidateCalculation();
    final generation = _generation;
    calculating = true;
    failure = null;
    notifyListeners();
    try {
      if (!checkOwnership()) return;
      final result = await _repository.calculate(
        lifetime: lifetime,
        date: now ?? DateTime.now(),
      );
      if (!checkOwnership() || generation != _generation) return;
      if (result is NutritionCalculated &&
          NutritionField.values.any(
            (f) => !nutritionValuesEqual(f, input(f), result.usedInputs[f]),
          )) {
        // Another device may have changed formula inputs. Never label those
        // server inputs as matching this visit's draft, nor offer adoption.
        throw const NutritionFailure(NutritionFailureType.unexpected);
      }
      calculation = result;
      calculating = false;
      notifyListeners();
    } catch (error) {
      if (!checkOwnership() || generation != _generation) return;
      calculating = false;
      failure = _safeFailure(error);
      notifyListeners();
    }
  }

  Future<NutritionSaveResult> confirm() async {
    if (!checkOwnership()) return NutritionSaveResult.stale;
    if (!loaded || step != 5 || saving || calculating || dirty) {
      return NutritionSaveResult.rejected;
    }
    if (targets.any && !useEstimate) {
      return NutritionSaveResult.finishedWithoutWrite;
    }
    final shown = calculation;
    if (shown is! NutritionCalculated) return NutritionSaveResult.rejected;
    saving = true;
    failure = null;
    notifyListeners();
    try {
      if (!checkOwnership()) return NutritionSaveResult.stale;
      // Apply exactly the visible snapshot. There is deliberately no unseen
      // recalculation and no cross-device optimistic concurrency guarantee.
      final profile = await _repository.save(
        lifetime: lifetime,
        changes: NutritionPatch.targets(shown.targets),
      );
      if (!checkOwnership()) return NutritionSaveResult.stale;
      if (!profile.targets.complete ||
          profile.targets.calories != shown.targets.calories ||
          profile.targets.protein != shown.targets.protein ||
          profile.targets.carbs != shown.targets.carbs ||
          profile.targets.fat != shown.targets.fat) {
        // The write may have committed; retain the shown snapshot for explicit
        // retry without publishing an unconfirmed result or compensating.
        throw const NutritionFailure(NutritionFailureType.unexpected);
      }
      targets = profile.targets;
      saving = false;
      notifyListeners();
      return NutritionSaveResult.targetsApplied;
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
    _invalidateCalculation();
    _preferenceInput.clear();
    _preferenceSaved.clear();
    _lists.clear();
    _savedLists.clear();
    preferenceErrors.clear();
    targets = const NutritionTargets();
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

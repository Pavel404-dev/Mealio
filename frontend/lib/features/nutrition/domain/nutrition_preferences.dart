import 'package:flutter/foundation.dart';

import 'nutrition_profile.dart';

/// A nullable value is distinct from an omitted PATCH member.
class NutritionChange<T> {
  const NutritionChange(this.value);
  final T value;
}

class NutritionBudget {
  const NutritionBudget(this.amount, this.currency);
  final String amount;
  final String currency;
}

enum PreferenceField { diet, cookingTime, budgetAmount, currency }

enum PreferenceList { allergies, likes, dislikes }

enum PreferenceError { diet, cookingTime, budgetAmount, currency, budgetPair }

PreferenceError? preferenceError(PreferenceField field, String input) {
  final value = input.trim();
  if (value.isEmpty) return null;
  return switch (field) {
    PreferenceField.diet =>
      value.runes.length <= 100 ? null : PreferenceError.diet,
    PreferenceField.cookingTime =>
      RegExp(r'^[0-9]{1,3}$').hasMatch(value) &&
              int.parse(value) >= 1 &&
              int.parse(value) <= 480
          ? null
          : PreferenceError.cookingTime,
    PreferenceField.budgetAmount =>
      validMoney(value) ? null : PreferenceError.budgetAmount,
    PreferenceField.currency =>
      RegExp(r'^[a-zA-Z]{3}$').hasMatch(value)
          ? null
          : PreferenceError.currency,
  };
}

bool validMoney(String value) {
  if (!RegExp(r'^[0-9]{1,7}(?:[.,][0-9]{1,2})?$').hasMatch(value)) return false;
  final cents = moneyCents(value);
  return cents >= 1 && cents <= 100000000;
}

int moneyCents(String value) {
  final parts = value.replaceAll(',', '.').split('.');
  return int.parse(
    '${parts[0]}${(parts.length == 2 ? parts[1] : '').padRight(2, '0')}',
  );
}

List<String> normalizeIngredients(List<String> values) =>
    values.map((v) => v.trim()).where((v) => v.isNotEmpty).toList();

class NutritionPreferences {
  NutritionPreferences({
    required this.diet,
    required this.cookingTime,
    required this.budget,
    required List<String> allergies,
    required List<String> likes,
    required List<String> dislikes,
  }) : allergies = List.unmodifiable(allergies),
       likes = List.unmodifiable(likes),
       dislikes = List.unmodifiable(dislikes);

  final String? diet;
  final int? cookingTime;
  final NutritionBudget? budget;
  final List<String> allergies, likes, dislikes;

  factory NutritionPreferences.fromJson(Map<String, dynamic> json) {
    Object? requiredValue(String key) {
      if (!json.containsKey(key)) {
        throw const FormatException('Incomplete preferences');
      }
      return json[key];
    }

    String? nullableText(String key) {
      final value = requiredValue(key);
      if (value != null && value is! String) {
        throw const FormatException('Invalid preference');
      }
      return value as String?;
    }

    List<String> strings(String key) {
      final value = requiredValue(key);
      if (value is! List || value.any((v) => v is! String)) {
        throw const FormatException('Invalid preference list');
      }
      return value.cast<String>();
    }

    final diet = nullableText('diet_type');
    final time = requiredValue('max_cooking_time_minutes');
    final amount = nullableText('weekly_food_budget_amount');
    final currency = nullableText('budget_currency');
    if ((diet != null && diet.runes.length > 100) ||
        (time != null && (time is! int || time < 1 || time > 480)) ||
        (amount == null) != (currency == null) ||
        (amount != null && (!validMoney(amount) || amount.contains(','))) ||
        (currency != null && !RegExp(r'^[A-Z]{3}$').hasMatch(currency))) {
      throw const FormatException('Invalid preferences');
    }
    return NutritionPreferences(
      diet: diet,
      cookingTime: time as int?,
      budget: amount == null ? null : NutritionBudget(amount, currency!),
      allergies: strings('allergies'),
      likes: strings('liked_ingredients'),
      dislikes: strings('disliked_ingredients'),
    );
  }

  List<String> list(PreferenceList field) => switch (field) {
    PreferenceList.allergies => allergies,
    PreferenceList.likes => likes,
    PreferenceList.dislikes => dislikes,
  };
  String text(PreferenceField field) => switch (field) {
    PreferenceField.diet => diet ?? '',
    PreferenceField.cookingTime => cookingTime?.toString() ?? '',
    PreferenceField.budgetAmount => budget?.amount ?? '',
    PreferenceField.currency => budget?.currency ?? '',
  };
}

class NutritionTargets {
  const NutritionTargets({this.calories, this.protein, this.carbs, this.fat});
  final int? calories, protein, carbs, fat;
  bool get any =>
      calories != null || protein != null || carbs != null || fat != null;
  bool get complete =>
      calories != null && protein != null && carbs != null && fat != null;
  factory NutritionTargets.fromJson(Map<String, dynamic> json) {
    int? read(String key) {
      if (!json.containsKey(key)) throw const FormatException('Missing target');
      final value = json[key];
      if (value != null && (value is! int || value < 1 || value > 2147483647)) {
        throw const FormatException('Invalid target');
      }
      return value as int?;
    }

    return NutritionTargets(
      calories: read('daily_calories_target'),
      protein: read('daily_protein_target_g'),
      carbs: read('daily_carbs_target_g'),
      fat: read('daily_fat_target_g'),
    );
  }
}

/// Deliberate operation-specific serializers; never serialize a full profile.
class NutritionPatch {
  NutritionPatch._(Map<String, Object?> json) : json = Map.unmodifiable(json);
  final Map<String, Object?> json;
  bool get isEmpty => json.isEmpty;

  factory NutritionPatch.formula(Map<NutritionField, String> changes) {
    if (changes.entries.any(
      (e) => nutritionInputError(e.key, e.value) != null,
    )) {
      throw const FormatException('Invalid formula inputs');
    }
    return NutritionPatch._({
      for (final e in changes.entries)
        e.key.wireName: nutritionWireValue(e.value),
    });
  }

  factory NutritionPatch.food({
    NutritionChange<String?>? diet,
    NutritionChange<List<String>>? allergies,
    NutritionChange<List<String>>? likes,
    NutritionChange<List<String>>? dislikes,
  }) {
    if (diet?.value != null &&
        preferenceError(PreferenceField.diet, diet!.value!) != null) {
      throw const FormatException('Invalid diet');
    }
    final normalizedDiet = diet?.value?.trim();
    return NutritionPatch._({
      if (diet != null)
        'diet_type': normalizedDiet == '' ? null : normalizedDiet,
      if (allergies != null)
        'allergies': List.unmodifiable(normalizeIngredients(allergies.value)),
      if (likes != null)
        'liked_ingredients': List.unmodifiable(
          normalizeIngredients(likes.value),
        ),
      if (dislikes != null)
        'disliked_ingredients': List.unmodifiable(
          normalizeIngredients(dislikes.value),
        ),
    });
  }

  factory NutritionPatch.practical({
    NutritionChange<int?>? cookingTime,
    NutritionChange<NutritionBudget?>? budget,
  }) {
    final time = cookingTime?.value;
    final pair = budget?.value;
    if ((time != null && (time < 1 || time > 480)) ||
        (pair != null &&
            (!validMoney(pair.amount) ||
                preferenceError(PreferenceField.currency, pair.currency) !=
                    null ||
                pair.currency.trim().isEmpty))) {
      throw const FormatException('Invalid practical preferences');
    }
    return NutritionPatch._({
      if (cookingTime != null) 'max_cooking_time_minutes': time,
      if (budget != null) ...{
        'weekly_food_budget_amount': pair?.amount.replaceAll(',', '.'),
        'budget_currency': pair?.currency.trim().toUpperCase(),
      },
    });
  }

  factory NutritionPatch.targets(NutritionTargets targets) {
    if (!targets.complete ||
        [
          targets.calories!,
          targets.protein!,
          targets.carbs!,
          targets.fat!,
        ].any((n) => n < 1 || n > 2147483647)) {
      throw const FormatException('Invalid targets');
    }
    return NutritionPatch._({
      'daily_calories_target': targets.calories,
      'daily_protein_target_g': targets.protein,
      'daily_carbs_target_g': targets.carbs,
      'daily_fat_target_g': targets.fat,
    });
  }
}

bool ingredientListsEqual(List<String> a, List<String> b) =>
    listEquals(normalizeIngredients(a), b);

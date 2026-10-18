import 'package:mealio/features/nutrition/data/nutrition_repository.dart';
import 'package:mealio/features/nutrition/domain/nutrition_profile.dart';
import 'package:mealio/features/nutrition/domain/nutrition_preferences.dart';
import 'package:mealio/features/nutrition/domain/nutrition_calculation.dart';

Map<String, dynamic> nutritionJson({bool full = false}) => {
  'goal': 'maintain',
  'sex': full ? 'female' : null,
  'birth_date': full ? '1992-02-29' : null,
  'height_cm': full ? '170.0' : null,
  'weight_kg': full ? '70.25' : null,
  'activity_level': full ? 'moderately_active' : null,
  'diet_type': 'balanced',
  'daily_calories_target': 2400,
  'daily_protein_target_g': 100,
  'daily_carbs_target_g': null,
  'daily_fat_target_g': null,
  'allergies': ['synthetic-allergen'],
  'liked_ingredients': <String>[],
  'disliked_ingredients': ['synthetic-dislike'],
  'preferred_meals_per_day': 3,
  'max_cooking_time_minutes': 45,
  'weekly_food_budget_amount': '80.00',
  'budget_currency': 'EUR',
};

class FakeNutritionRepository implements NutritionRepository {
  FakeNutritionRepository({Map<String, dynamic>? json})
    : json = json ?? nutritionJson();

  final Map<String, dynamic> json;
  Future<NutritionProfile> Function()? loadHandler;
  Future<NutritionProfile> Function(NutritionPatch)? saveHandler;
  Future<NutritionCalculation> Function(DateTime)? calculateHandler;
  int calculations = 0;
  final patches = <Map<String, Object?>>[];
  int loads = 0;
  final saves = <Map<NutritionField, String>>[];
  final lifetimes = <int>[];

  @override
  Future<NutritionProfile> load({required int lifetime}) {
    loads++;
    lifetimes.add(lifetime);
    return loadHandler?.call() ?? Future.value(NutritionProfile.fromJson(json));
  }

  @override
  Future<NutritionProfile> save({
    required int lifetime,
    required NutritionPatch changes,
  }) {
    patches.add(changes.json);
    saves.add({
      for (final f in NutritionField.values)
        if (changes.json.containsKey(f.wireName))
          f: changes.json[f.wireName] as String,
    });
    lifetimes.add(lifetime);
    if (saveHandler != null) return saveHandler!(changes);
    json.addAll(changes.json);
    return Future.value(NutritionProfile.fromJson(json));
  }

  @override
  Future<NutritionCalculation> calculate({
    required int lifetime,
    required DateTime date,
  }) {
    calculations++;
    lifetimes.add(lifetime);
    return calculateHandler?.call(date) ??
        Future.value(
          NutritionCalculation.fromJson(
            calculationJson(
              date: nutritionCalculationDate(date),
              profile: json,
            ),
            date: nutritionCalculationDate(date),
          ),
        );
  }
}

Map<String, dynamic> calculationJson({
  String date = '2026-10-04',
  Map<String, dynamic>? profile,
}) => {
  'rules_version': 'mealio-nutrition-v1',
  'calculation_date': date,
  'status': 'calculated',
  'result': {
    'age_years': 30,
    'used_inputs': profile == null
        ? {
            'goal': 'maintain',
            'sex': 'male',
            'birth_date': '1996-10-04',
            'height_cm': '180.0',
            'weight_kg': '80.00',
            'activity_level': 'moderately_active',
          }
        : {
            for (final f in NutritionField.values)
              f.wireName: profile[f.wireName],
          },
    'activity_factor': '1.80',
    'goal_factor': '1.00',
    'ree_kcal': '1780.00',
    'tdee_kcal': '3204.00',
    'calories_target_kcal': 3204,
    'protein_target_g': 160,
    'fat_target_g': 107,
    'carbs_target_g': 400,
    'energy_delta_kcal': -1,
  },
};

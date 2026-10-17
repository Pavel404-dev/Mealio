import 'package:mealio/features/nutrition/data/nutrition_repository.dart';
import 'package:mealio/features/nutrition/domain/nutrition_profile.dart';

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
  Future<NutritionProfile> Function(Map<NutritionField, String>)? saveHandler;
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
    required Map<NutritionField, String> changes,
  }) {
    saves.add(Map.of(changes));
    lifetimes.add(lifetime);
    if (saveHandler != null) return saveHandler!(changes);
    for (final entry in changes.entries) {
      json[entry.key.wireName] = entry.value;
    }
    return Future.value(NutritionProfile.fromJson(json));
  }
}

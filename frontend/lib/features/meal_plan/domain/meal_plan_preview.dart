enum MealPlanSlot { breakfast, lunch, dinner, snack }

class MealPlanPreviewRequest {
  MealPlanPreviewRequest({
    required DateTime date,
    required this.locale,
    required Iterable<MealPlanSlot> slots,
  }) : plannedDate = date.toIso8601String().split('T').first,
       slots = List.unmodifiable(slots) {
    if (date.year < 1 ||
        date.year > 9999 ||
        !const {'en', 'ru', 'uk', 'sk'}.contains(locale) ||
        this.slots.isEmpty ||
        this.slots.toSet().length != this.slots.length) {
      throw ArgumentError('Invalid meal plan preview request');
    }
  }

  final String plannedDate;
  final String locale;
  final List<MealPlanSlot> slots;

  Map<String, Object> toJson() => {
    'planned_date': plannedDate,
    'locale': locale,
    'meal_types': slots.map((slot) => slot.name).toList(),
  };
}

enum MealPlanTargetFit { withinTolerance, outsideTolerance, notEvaluated }

final _recipeIdPattern = RegExp(
  r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
  caseSensitive: false,
);

class MealPlanPreview {
  const MealPlanPreview._({
    required this.items,
    required this.calories,
    required this.proteinG,
    required this.carbsG,
    required this.fatG,
    required this.targetFit,
    required this.tolerancePercent,
  });

  factory MealPlanPreview.fromJson(
    Object? value,
    MealPlanPreviewRequest request,
  ) {
    final json = _object(value);
    final rows = json['items'];
    if (rows is! List || rows.length != request.slots.length) {
      throw const FormatException('Invalid preview items');
    }
    final items = <MealPlanPreviewItem>[];
    for (var index = 0; index < rows.length; index++) {
      final row = _object(rows[index]);
      final slot = request.slots[index];
      final recipeId = row['recipe_id'];
      final servings = _decimal(row['planned_servings']);
      if (row['planned_date'] != request.plannedDate ||
          row['meal_type'] != slot.name ||
          recipeId is! String ||
          !_recipeIdPattern.hasMatch(recipeId) ||
          servings < 0.01 ||
          servings > 12) {
        throw const FormatException('Mismatched preview item');
      }
      items.add(MealPlanPreviewItem(slot, recipeId, servings));
    }

    final nutrition = _object(json['nutrition']);
    final fit = _object(json['target_fit']);
    final tolerance = fit['tolerance_percent'];
    if (tolerance is! int || tolerance <= 0) {
      throw const FormatException('Invalid target tolerance');
    }
    return MealPlanPreview._(
      items: List.unmodifiable(items),
      calories: _decimal(nutrition['total_calories']),
      proteinG: _decimal(nutrition['total_protein_g']),
      carbsG: _decimal(nutrition['total_carbs_g']),
      fatG: _decimal(nutrition['total_fat_g']),
      targetFit: switch (fit['status']) {
        'within_tolerance' => MealPlanTargetFit.withinTolerance,
        'outside_tolerance' => MealPlanTargetFit.outsideTolerance,
        'not_evaluated' => MealPlanTargetFit.notEvaluated,
        _ => throw const FormatException('Invalid target fit'),
      },
      tolerancePercent: tolerance,
    );
  }

  final List<MealPlanPreviewItem> items;
  final double calories;
  final double proteinG;
  final double carbsG;
  final double fatG;
  final MealPlanTargetFit targetFit;
  final int tolerancePercent;
}

class MealPlanPreviewItem {
  const MealPlanPreviewItem(this.slot, this.recipeId, this.servings);

  final MealPlanSlot slot;
  final String recipeId;
  final double servings;
}

Map<String, dynamic> _object(Object? value) {
  if (value is! Map<String, dynamic>) {
    throw const FormatException('Invalid meal plan preview object');
  }
  return value;
}

double _decimal(Object? value) {
  final parsed = value is String ? double.tryParse(value) : null;
  if (parsed == null || !parsed.isFinite || parsed < 0) {
    throw const FormatException('Invalid meal plan preview decimal');
  }
  return parsed;
}

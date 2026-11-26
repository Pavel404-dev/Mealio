import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/localization/l10n.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../../auth/presentation/auth_controller.dart';
import '../../recipes/data/recipe_repository.dart';
import '../../recipes/presentation/recipe_localization.dart';
import '../data/meal_plan_preview_repository.dart';
import '../domain/meal_plan_preview.dart';
import '../domain/meal_plan_preview_failure.dart';
import 'meal_plan_preview_controller.dart';

class MealPlanPreviewScreen extends ConsumerWidget {
  const MealPlanPreviewScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final storage = ref.watch(secureStorageServiceProvider);
    if (auth.isLoading || auth.asData?.value.isAuthenticated != true) {
      return const SizedBox.shrink();
    }
    return _PreviewForm(key: ValueKey(storage.sessionLifetime));
  }
}

class _PreviewForm extends ConsumerStatefulWidget {
  const _PreviewForm({super.key});

  @override
  ConsumerState<_PreviewForm> createState() => _PreviewFormState();
}

class _PreviewFormState extends ConsumerState<_PreviewForm> {
  final _days = <DateTime, _DayPreview>{};
  DateTime _date = DateUtils.dateOnly(DateTime.now());

  MealPlanPreviewController get _controller => _days[_date]!.controller;
  Set<MealPlanSlot> get _slots => _days[_date]!.slots;

  @override
  void initState() {
    super.initState();
    _days[_date] = _createDay(const {
      MealPlanSlot.breakfast,
      MealPlanSlot.lunch,
      MealPlanSlot.dinner,
    });
    ref.listenManual(authControllerProvider, (_, _) {
      for (final day in _days.values) {
        day.controller.checkOwnership();
      }
    });
  }

  _DayPreview _createDay(Set<MealPlanSlot> slots) => _DayPreview(
    slots: Set.of(slots),
    controller: MealPlanPreviewController(
      repository: ref.read(mealPlanPreviewRepositoryProvider),
      recipes: ref.read(recipeRepositoryProvider),
      storage: ref.read(secureStorageServiceProvider),
      isAuthenticated: () {
        final auth = ref.read(authControllerProvider);
        return !auth.isLoading && auth.asData?.value.isAuthenticated == true;
      },
    ),
  );

  @override
  void dispose() {
    for (final day in _days.values) {
      day.controller.dispose();
    }
    super.dispose();
  }

  Future<void> _selectDate() async {
    if (!_controller.isCurrent || _controller.loading) return;
    final date = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(1),
      lastDate: DateTime(9999, 12, 31),
    );
    if (!mounted ||
        !_controller.isCurrent ||
        _controller.loading ||
        date == null ||
        DateUtils.isSameDay(date, _date)) {
      return;
    }
    final nextDate = DateUtils.dateOnly(date);
    setState(() {
      _days.putIfAbsent(nextDate, () => _createDay(_slots));
      _date = nextDate;
    });
  }

  void _generate() {
    if (_controller.failure != null) {
      unawaited(_controller.retry());
      return;
    }
    unawaited(
      _controller.generate(
        MealPlanPreviewRequest(
          date: _date,
          locale: Localizations.localeOf(context).languageCode,
          slots: MealPlanSlot.values.where(_slots.contains),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, _) {
      if (!_controller.isCurrent) return const SizedBox.shrink();
      final l10n = context.l10n;
      final loading = _controller.loading;
      final failure = _controller.failure;
      final preview = _controller.preview;
      return Scaffold(
        key: const Key('meal-plan-preview-screen'),
        appBar: AppBar(title: Text(l10n.mealPlan)),
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 560),
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 12, 20, 32),
                children: [
                  Text(
                    l10n.mealPlanDate,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton.icon(
                    key: const Key('meal-plan-preview-date'),
                    onPressed: loading ? null : _selectDate,
                    icon: const Icon(Icons.calendar_today_outlined),
                    label: Text(
                      MaterialLocalizations.of(context).formatFullDate(_date),
                    ),
                  ),
                  const SizedBox(height: 20),
                  Text(
                    l10n.mealPlanMealTypes,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 8,
                    runSpacing: 4,
                    children: [
                      for (final slot in MealPlanSlot.values)
                        FilterChip(
                          key: ValueKey('meal-plan-slot-${slot.name}'),
                          label: Text(_slotLabel(context, slot)),
                          selected: _slots.contains(slot),
                          onSelected: loading
                              ? null
                              : (selected) {
                                  if (_controller.loading) return;
                                  setState(() {
                                    if (selected) {
                                      _slots.add(slot);
                                    } else {
                                      _slots.remove(slot);
                                    }
                                  });
                                  _controller.reset();
                                },
                        ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  if (failure != null) ...[
                    Semantics(
                      liveRegion: true,
                      child: Text(
                        _failureMessage(context, failure.type),
                        key: const Key('meal-plan-preview-error'),
                        style: TextStyle(
                          color: Theme.of(context).colorScheme.error,
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],
                  FilledButton.icon(
                    key: const Key('meal-plan-preview-generate'),
                    onPressed: loading || _slots.isEmpty ? null : _generate,
                    icon: loading
                        ? const SizedBox.square(
                            dimension: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.auto_awesome_outlined),
                    label: Text(
                      loading
                          ? l10n.mealPlanGenerating
                          : failure != null
                          ? l10n.retry
                          : preview != null
                          ? l10n.mealPlanRegenerate
                          : l10n.mealPlanGenerate,
                    ),
                  ),
                  if (preview != null) ...[
                    const SizedBox(height: 24),
                    _PreviewResult(
                      preview: preview,
                      recipeTitles: _controller.recipeTitles,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      );
    },
  );
}

class _DayPreview {
  const _DayPreview({required this.slots, required this.controller});

  final Set<MealPlanSlot> slots;
  final MealPlanPreviewController controller;
}

class _PreviewResult extends StatelessWidget {
  const _PreviewResult({required this.preview, required this.recipeTitles});

  final MealPlanPreview preview;
  final Map<String, String> recipeTitles;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    String number(double value) => formatRecipeNumber(context, value);
    final fit = switch (preview.targetFit) {
      MealPlanTargetFit.withinTolerance => l10n.mealPlanWithinTolerance(
        preview.tolerancePercent,
      ),
      MealPlanTargetFit.outsideTolerance => l10n.mealPlanOutsideTolerance(
        preview.tolerancePercent,
      ),
      MealPlanTargetFit.notEvaluated => null,
    };
    return Column(
      key: const Key('meal-plan-preview-result'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  l10n.mealPlanDailyTotals,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Text(l10n.recipeCalories(number(preview.calories))),
                Text(l10n.recipeProtein(number(preview.proteinG))),
                Text(l10n.recipeCarbs(number(preview.carbsG))),
                Text(l10n.recipeFat(number(preview.fatG))),
                if (fit != null) ...[const SizedBox(height: 8), Text(fit)],
              ],
            ),
          ),
        ),
        for (final item in preview.items)
          Card(
            child: ListTile(
              key: ValueKey('meal-plan-preview-${item.slot.name}'),
              title: Text(_slotLabel(context, item.slot)),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(recipeTitles[item.recipeId] ?? l10n.mealPlanOpenRecipe),
                  Text(l10n.mealPlanPortions(number(item.servings))),
                ],
              ),
              trailing: const Icon(Icons.chevron_right_rounded),
              onTap: () => context.push(
                '/recipes/${Uri.encodeComponent(item.recipeId)}',
              ),
            ),
          ),
      ],
    );
  }
}

String _slotLabel(BuildContext context, MealPlanSlot slot) => switch (slot) {
  MealPlanSlot.breakfast => context.l10n.mealPlanBreakfast,
  MealPlanSlot.lunch => context.l10n.mealPlanLunch,
  MealPlanSlot.dinner => context.l10n.mealPlanDinner,
  MealPlanSlot.snack => context.l10n.mealPlanSnack,
};

String _failureMessage(BuildContext context, MealPlanPreviewFailureType type) =>
    switch (type) {
      MealPlanPreviewFailureType.authentication =>
        context.l10n.mealPlanAuthentication,
      MealPlanPreviewFailureType.noEligibleRecipes =>
        context.l10n.mealPlanNoEligibleRecipes,
      MealPlanPreviewFailureType.inProgress => context.l10n.mealPlanInProgress,
      MealPlanPreviewFailureType.inputsChanged =>
        context.l10n.mealPlanInputsChanged,
      MealPlanPreviewFailureType.rateLimited => context.l10n.rateLimited,
      MealPlanPreviewFailureType.providerUnavailable =>
        context.l10n.mealPlanProviderUnavailable,
      MealPlanPreviewFailureType.connection => context.l10n.connectionError,
      MealPlanPreviewFailureType.unexpected => context.l10n.unexpectedError,
    };

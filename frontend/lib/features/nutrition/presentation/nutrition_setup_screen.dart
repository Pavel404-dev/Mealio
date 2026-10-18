import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/localization/l10n.dart';
import '../../../core/localization/language_button.dart';
import '../../../core/storage/secure_storage_provider.dart';
import '../../auth/presentation/auth_controller.dart';
import '../data/nutrition_repository.dart';
import '../domain/nutrition_profile.dart';
import '../domain/nutrition_preferences.dart';
import '../domain/nutrition_calculation.dart';
import 'nutrition_localization.dart';
import 'nutrition_setup_controller.dart';

class NutritionSetupScreen extends ConsumerWidget {
  const NutritionSetupScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final storage = ref.watch(secureStorageServiceProvider);
    if (auth.asData?.value.isAuthenticated != true || auth.isLoading) {
      return const SizedBox.shrink();
    }
    // Auth changes trigger this read of the mutable lifetime. Same-lifetime
    // user reloads and token rotation keep the existing route-local draft.
    return _NutritionWizard(key: ValueKey(storage.sessionLifetime));
  }
}

class _NutritionWizard extends ConsumerStatefulWidget {
  const _NutritionWizard({super.key});

  @override
  ConsumerState<_NutritionWizard> createState() => _NutritionWizardState();
}

class _NutritionWizardState extends ConsumerState<_NutritionWizard> {
  late final NutritionSetupController _controller;
  bool _submitting = false;
  bool _confirmExit = false;

  @override
  void initState() {
    super.initState();
    _controller = NutritionSetupController(
      repository: ref.read(nutritionRepositoryProvider),
      storage: ref.read(secureStorageServiceProvider),
      isAuthenticated: () {
        final auth = ref.read(authControllerProvider);
        return !auth.isLoading && auth.asData?.value.isAuthenticated == true;
      },
    );
    ref.listenManual(authControllerProvider, (_, _) {
      _controller.checkOwnership();
    });
    unawaited(_controller.load());
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  bool get _locked => _submitting || _controller.saving;

  Future<void> _save() async {
    if (_locked || _confirmExit || !_controller.checkOwnership()) return;
    setState(() => _submitting = true);
    final result = await _controller.save();
    if (!mounted || !_controller.checkOwnership()) return;
    setState(() => _submitting = false);
    if (result == NutritionSaveResult.finishedWithoutWrite ||
        result == NutritionSaveResult.targetsApplied) {
      _leave(targetsApplied: result == NutritionSaveResult.targetsApplied);
    }
  }

  void _back() {
    if (_locked || !_controller.checkOwnership()) return;
    if (_confirmExit) {
      setState(() => _confirmExit = false);
    } else if (_controller.step > 0) {
      _controller.back();
    } else {
      _requestExit();
    }
  }

  void _requestExit() {
    if (_locked || !_controller.checkOwnership()) return;
    if (_controller.dirty) {
      setState(() => _confirmExit = true);
    } else {
      _leave();
    }
  }

  void _leave({bool targetsApplied = false}) {
    if (!mounted || _locked || !_controller.checkOwnership()) return;
    if (targetsApplied) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Builder(
            builder: (context) => Text(context.l10n.nutritionSaved),
          ),
        ),
      );
    }
    context.go('/home');
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, _) {
      if (!_controller.isCurrent) return const SizedBox.shrink();
      final l10n = context.l10n;
      return PopScope(
        canPop: false,
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop) _back();
        },
        child: Scaffold(
          key: const Key('nutrition-setup-screen'),
          appBar: AppBar(
            title: Text(l10n.nutritionSetup),
            leading: IconButton(
              key: const Key('nutrition-back'),
              tooltip: l10n.back,
              onPressed: _locked ? null : _back,
              icon: const Icon(Icons.arrow_back_rounded),
            ),
            actions: const [LanguageButton()],
          ),
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
              children: _confirmExit
                  ? [
                      Semantics(
                        liveRegion: true,
                        child: Text(
                          l10n.nutritionDiscardTitle,
                          style: Theme.of(context).textTheme.headlineSmall,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Text(l10n.nutritionDiscardDescription),
                      const SizedBox(height: 20),
                      FilledButton(
                        key: const Key('nutrition-stay'),
                        onPressed: () => setState(() => _confirmExit = false),
                        child: Text(l10n.nutritionStay),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton(
                        key: const Key('nutrition-discard'),
                        onPressed: _leave,
                        child: Text(l10n.nutritionLeaveDiscard),
                      ),
                    ]
                  : [
                      Text(l10n.nutritionDescription),
                      const SizedBox(height: 20),
                      if (_controller.loading) ...[
                        Text(l10n.nutritionLoading),
                        const SizedBox(height: 12),
                        LinearProgressIndicator(
                          semanticsLabel: l10n.nutritionLoading,
                        ),
                      ],
                      if (_controller.loaded) ...[
                        Semantics(
                          liveRegion: true,
                          child: Text(
                            l10n.nutritionStep(
                              _controller.step + 1,
                              NutritionSetupController.stepCount,
                            ),
                            key: const Key('nutrition-step'),
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(switch (_controller.step) {
                          0 => l10n.nutritionGoal,
                          1 => l10n.nutritionBody,
                          2 => l10n.nutritionActivity,
                          3 => l10n.nutritionFood,
                          4 => l10n.nutritionPractical,
                          _ => l10n.nutritionSummary,
                        }, style: Theme.of(context).textTheme.headlineSmall),
                        if (_controller.lastSaveWrote != null) ...[
                          const SizedBox(height: 12),
                          Semantics(
                            liveRegion: true,
                            child: Text(
                              _controller.lastSaveWrote!
                                  ? l10n.nutritionStepSaved
                                  : l10n.nutritionNoChanges,
                            ),
                          ),
                        ],
                        for (final field in NutritionField.values.where(
                          (field) => field.step == _controller.step,
                        )) ...[const SizedBox(height: 20), _field(field)],
                        if (_controller.step == 3 || _controller.step == 4)
                          ..._preferences(),
                        if (_controller.step == 5) ..._summary(),
                      ],
                      if (_controller.failure case final failure?) ...[
                        const SizedBox(height: 16),
                        Semantics(
                          liveRegion: true,
                          child: Text(
                            nutritionFailureLabel(failure, l10n),
                            key: const Key('nutrition-error'),
                            style: TextStyle(
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                        ),
                        if (!_controller.loaded)
                          FilledButton(
                            key: const Key('nutrition-retry'),
                            onPressed: _controller.loading
                                ? null
                                : _controller.load,
                            child: Text(l10n.retry),
                          ),
                      ],
                      if (_controller.loaded) ...[
                        const SizedBox(height: 24),
                        FilledButton(
                          key: const Key('nutrition-save'),
                          onPressed:
                              _locked ||
                                  (_controller.step == 5 &&
                                      (_controller.calculating ||
                                          _controller.dirty ||
                                          (!_controller.targets.any &&
                                              _controller.calculation
                                                  is! NutritionCalculated)))
                              ? null
                              : _save,
                          child: Text(
                            _locked
                                ? l10n.nutritionSaving
                                : _controller.step == 5
                                ? (_controller.targets.any &&
                                          !_controller.useEstimate
                                      ? l10n.nutritionKeepTargets
                                      : l10n.nutritionApplyEstimate)
                                : l10n.nutritionSaveContinue,
                          ),
                        ),
                      ],
                      const SizedBox(height: 12),
                      TextButton(
                        key: const Key('nutrition-exit'),
                        onPressed: _locked ? null : _requestExit,
                        child: Text(l10n.nutritionReturnHome),
                      ),
                    ],
            ),
          ),
        ),
      );
    },
  );

  List<Widget> _preferences() {
    final l10n = context.l10n;
    return [
      for (final field in PreferenceField.values.where(
        (f) => (f == PreferenceField.diet ? 3 : 4) == _controller.step,
      )) ...[
        const SizedBox(height: 20),
        _PreferenceInput(
          key: ValueKey('preference-${field.name}'),
          value: _controller.preferenceInput(field),
          enabled: !_locked,
          label: preferenceFieldLabel(field, l10n),
          error: preferenceErrorLabel(
            _controller.preferenceErrors[field],
            l10n,
          ),
          keyboardType: switch (field) {
            PreferenceField.cookingTime => TextInputType.number,
            PreferenceField.budgetAmount =>
              const TextInputType.numberWithOptions(decimal: true),
            _ => TextInputType.text,
          },
          onChanged: (value) => _controller.editPreference(field, value),
        ),
      ],
      if (_controller.step == 4)
        TextButton(
          key: const Key('nutrition-clear-budget'),
          onPressed: _locked
              ? null
              : () {
                  _controller.editPreference(PreferenceField.budgetAmount, '');
                  _controller.editPreference(PreferenceField.currency, '');
                },
          child: Text(l10n.nutritionClearBudget),
        ),
      if (_controller.step == 3)
        for (final field in PreferenceList.values) ...[
          const SizedBox(height: 20),
          _IngredientEditor(
            key: ValueKey('ingredients-${field.name}'),
            label: preferenceListLabel(field, l10n),
            values: _controller.ingredients(field),
            enabled: !_locked,
            onChanged: (values) => _controller.editIngredients(field, values),
          ),
        ],
    ];
  }

  List<Widget> _targetValues(NutritionTargets targets) {
    final l10n = context.l10n;
    return [
      Text(
        '${l10n.nutritionCalories}: ${targets.calories ?? l10n.nutritionNotSet}',
      ),
      Text(
        '${l10n.nutritionProtein}: ${targets.protein ?? l10n.nutritionNotSet}',
      ),
      Text('${l10n.nutritionCarbs}: ${targets.carbs ?? l10n.nutritionNotSet}'),
      Text('${l10n.nutritionFat}: ${targets.fat ?? l10n.nutritionNotSet}'),
    ];
  }

  List<Widget> _summary() {
    final l10n = context.l10n;
    final outcome = _controller.calculation;
    return [
      const SizedBox(height: 16),
      Text(l10n.nutritionSummaryNote),
      const SizedBox(height: 16),
      Text(
        l10n.nutritionSavedTargets,
        style: Theme.of(context).textTheme.titleMedium,
      ),
      ..._targetValues(_controller.targets),
      if (_controller.dirty) Text(l10n.nutritionSaveInputsFirst),
      const SizedBox(height: 16),
      if (outcome != null)
        Text(
          l10n.nutritionCalculationDetails(
            outcome.date,
            NutritionCalculation.rulesVersion,
          ),
        ),
      if (outcome is NutritionCalculated) ...[
        Text(
          l10n.nutritionEstimate,
          style: Theme.of(context).textTheme.titleMedium,
        ),
        ..._targetValues(outcome.targets),
        if (_controller.targets.any)
          CheckboxListTile(
            key: const Key('nutrition-select-estimate'),
            contentPadding: EdgeInsets.zero,
            title: Text(l10n.nutritionUseEstimate),
            value: _controller.useEstimate,
            onChanged: _locked || _controller.calculating
                ? null
                : (value) => _controller.selectEstimate(value ?? false),
          ),
      ],
      if (outcome is NutritionIncomplete) ...[
        Text(l10n.nutritionMissing),
        for (final field in outcome.missing)
          Text(nutritionFieldLabel(field, l10n)),
      ],
      if (outcome is NutritionUnsupported) ...[
        Text(l10n.nutritionUnsupported),
        for (final reason in outcome.reasons)
          Text(nutritionReasonLabel(reason, l10n)),
      ],
      if (_controller.calculating)
        LinearProgressIndicator(semanticsLabel: l10n.nutritionCalculating),
      OutlinedButton(
        key: const Key('nutrition-calculate'),
        onPressed:
            _locked || _controller.calculating || _controller.formulaDirty
            ? null
            : () => _controller.calculate(),
        child: Text(
          _controller.calculating
              ? l10n.nutritionCalculating
              : _controller.failure != null
              ? l10n.retry
              : l10n.nutritionCalculate,
        ),
      ),
    ];
  }

  Widget _field(NutritionField field) {
    final l10n = context.l10n;
    final value = _controller.input(field);
    final decoration = InputDecoration(
      labelText: nutritionFieldLabel(field, l10n),
      errorText: nutritionErrorLabel(_controller.error(field), l10n),
      errorMaxLines: 5,
      helperText: field == NutritionField.birthDate
          ? l10n.nutritionDateHint
          : null,
      helperMaxLines: 3,
    );
    if (field.choices.isNotEmpty) {
      return DropdownButtonFormField<String>(
        key: ValueKey('nutrition-${field.wireName}'),
        initialValue: value.isEmpty ? null : value,
        isExpanded: true,
        itemHeight: null,
        decoration: decoration,
        hint: Text(l10n.nutritionChoose),
        items: [
          for (final choice in field.choices)
            DropdownMenuItem(
              value: choice,
              child: Text(nutritionChoiceLabel(choice, l10n)),
            ),
        ],
        onChanged: _locked
            ? null
            : (value) {
                if (value != null) _controller.edit(field, value);
              },
      );
    }
    return TextFormField(
      key: ValueKey('nutrition-${field.wireName}'),
      initialValue: value,
      enabled: !_locked,
      decoration: decoration,
      keyboardType: field == NutritionField.birthDate
          ? TextInputType.datetime
          : const TextInputType.numberWithOptions(decimal: true),
      textInputAction: TextInputAction.next,
      autocorrect: false,
      onChanged: (value) => _controller.edit(field, value),
    );
  }
}

class _PreferenceInput extends StatefulWidget {
  const _PreferenceInput({
    super.key,
    required this.value,
    required this.label,
    required this.error,
    required this.enabled,
    required this.keyboardType,
    required this.onChanged,
  });
  final String value, label;
  final String? error;
  final bool enabled;
  final TextInputType keyboardType;
  final ValueChanged<String> onChanged;
  @override
  State<_PreferenceInput> createState() => _PreferenceInputState();
}

class _PreferenceInputState extends State<_PreferenceInput> {
  late final TextEditingController text = TextEditingController(
    text: widget.value,
  );
  @override
  void didUpdateWidget(_PreferenceInput oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (text.text != widget.value) text.text = widget.value;
  }

  @override
  void dispose() {
    text.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => TextField(
    controller: text,
    enabled: widget.enabled,
    keyboardType: widget.keyboardType,
    autocorrect: false,
    onChanged: widget.onChanged,
    decoration: InputDecoration(
      labelText: widget.label,
      errorText: widget.error,
      errorMaxLines: 5,
      suffixIcon: IconButton(
        tooltip: context.l10n.nutritionClear,
        onPressed: widget.enabled ? () => widget.onChanged('') : null,
        icon: const Icon(Icons.clear),
      ),
    ),
  );
}

class _IngredientEditor extends StatefulWidget {
  const _IngredientEditor({
    super.key,
    required this.label,
    required this.values,
    required this.enabled,
    required this.onChanged,
  });
  final String label;
  final List<String> values;
  final bool enabled;
  final ValueChanged<List<String>> onChanged;
  @override
  State<_IngredientEditor> createState() => _IngredientEditorState();
}

class _IngredientEditorState extends State<_IngredientEditor> {
  late final List<TextEditingController> entries = [
    for (final v in widget.values) TextEditingController(text: v),
  ];
  // Keep removed controllers alive until disposal: their TextFields can still
  // be mounted for the remainder of the current frame.
  final retired = <TextEditingController>[];
  void changed() => widget.onChanged([for (final e in entries) e.text]);
  @override
  void dispose() {
    for (final e in [...entries, ...retired]) {
      e.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(widget.label, style: Theme.of(context).textTheme.titleMedium),
      for (final entry in entries)
        Padding(
          key: ObjectKey(entry),
          padding: const EdgeInsets.only(top: 8),
          child: TextField(
            controller: entry,
            enabled: widget.enabled,
            onChanged: (_) => changed(),
            decoration: InputDecoration(
              labelText: context.l10n.nutritionIngredient,
              suffixIcon: IconButton(
                tooltip: context.l10n.nutritionRemoveIngredient,
                onPressed: !widget.enabled
                    ? null
                    : () {
                        setState(() {
                          entries.remove(entry);
                          retired.add(entry);
                        });
                        changed();
                      },
                icon: const Icon(Icons.remove_circle_outline),
              ),
            ),
          ),
        ),
      TextButton.icon(
        onPressed: !widget.enabled
            ? null
            : () {
                setState(() => entries.add(TextEditingController()));
                changed();
              },
        icon: const Icon(Icons.add),
        label: Text(context.l10n.nutritionAddIngredient),
      ),
    ],
  );
}

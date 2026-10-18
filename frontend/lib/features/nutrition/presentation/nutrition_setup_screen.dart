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
  bool _finished = false;

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
    if (result == NutritionSaveResult.finished) {
      _finished = true;
      _requestExit();
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

  void _leave() {
    if (!mounted || _locked || !_controller.checkOwnership()) return;
    if (_finished) {
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
                            l10n.nutritionStep(_controller.step + 1),
                            key: const Key('nutrition-step'),
                            style: Theme.of(context).textTheme.titleMedium,
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(switch (_controller.step) {
                          0 => l10n.nutritionGoal,
                          1 => l10n.nutritionBody,
                          _ => l10n.nutritionActivity,
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
                          onPressed: _locked ? null : _save,
                          child: Text(
                            _locked
                                ? l10n.nutritionSaving
                                : _controller.step == 2
                                ? l10n.nutritionSave
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

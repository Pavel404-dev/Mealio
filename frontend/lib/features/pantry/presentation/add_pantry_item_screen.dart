import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../../../core/localization/l10n.dart';
import '../data/pantry_repository.dart';
import '../domain/pantry_failure.dart';
import '../domain/pantry_item.dart';
import '../domain/pantry_quantity.dart';
import 'pantry_providers.dart';

class AddPantryItemScreen extends ConsumerStatefulWidget {
  const AddPantryItemScreen({super.key});

  @override
  ConsumerState<AddPantryItemScreen> createState() =>
      _AddPantryItemScreenState();
}

class _AddPantryItemScreenState extends ConsumerState<AddPantryItemScreen> {
  static const Duration _searchDebounce = Duration(milliseconds: 350);

  final _formKey = GlobalKey<FormState>();
  final _searchController = TextEditingController();
  final _quantityController = TextEditingController();

  Timer? _debounceTimer;
  List<Ingredient> _ingredients = const [];
  Ingredient? _selectedIngredient;
  DateTime? _expiresAt;
  PantryFailure? _searchFailure;
  PantryFailure? _submitFailure;
  bool _showIngredientError = false;
  String _normalizedInputQuery = '';
  String? _lastRequestedQuery;
  int _searchGeneration = 0;
  bool _isSearching = true;
  bool _isSubmitting = false;

  @override
  void initState() {
    super.initState();
    _searchController.addListener(_onSearchChanged);
    scheduleMicrotask(() => _loadIngredients(''));
  }

  @override
  void dispose() {
    _searchGeneration++;
    _debounceTimer?.cancel();
    _searchController.dispose();
    _quantityController.dispose();
    super.dispose();
  }

  void _onSearchChanged() {
    final query = _searchController.text.trim();
    if (query == _normalizedInputQuery) {
      return;
    }
    _normalizedInputQuery = query;
    _debounceTimer?.cancel();
    _searchGeneration++;
    _lastRequestedQuery = null;
    setState(() {
      _isSearching = true;
      _searchFailure = null;
      if (_submitFailure != null) {
        _submitFailure = null;
      }
    });
    _debounceTimer = Timer(_searchDebounce, () => _loadIngredients(query));
  }

  Future<void> _loadIngredients(String query, {bool force = false}) async {
    final normalizedQuery = query.trim();
    if (!force && normalizedQuery == _lastRequestedQuery) {
      return;
    }
    _lastRequestedQuery = normalizedQuery;
    final generation = ++_searchGeneration;
    if (mounted) {
      setState(() {
        _isSearching = true;
        _searchFailure = null;
      });
    }

    try {
      final ingredients = await ref
          .read(pantryRepositoryProvider)
          .searchIngredients(search: normalizedQuery);
      if (!mounted || generation != _searchGeneration) {
        return;
      }
      setState(() {
        _ingredients = ingredients;
        _isSearching = false;
      });
    } on PantryFailure catch (failure) {
      if (!mounted || generation != _searchGeneration) {
        return;
      }
      setState(() {
        _isSearching = false;
        _searchFailure = failure;
      });
    } catch (_) {
      if (!mounted || generation != _searchGeneration) {
        return;
      }
      setState(() {
        _isSearching = false;
        _searchFailure = PantryFailure.searchUnexpected();
      });
    }
  }

  void _selectIngredient(Ingredient ingredient) {
    setState(() {
      _selectedIngredient = ingredient;
      _showIngredientError = false;
      _submitFailure = null;
    });
  }

  Future<void> _pickExpiry() async {
    final now = DateTime.now();
    final currentExpiry = _expiresAt;
    final selected = await showDatePicker(
      context: context,
      initialDate: currentExpiry == null
          ? now
          : DateTime(
              currentExpiry.year,
              currentExpiry.month,
              currentExpiry.day,
            ),
      firstDate: DateTime(now.year - 10),
      lastDate: DateTime(now.year + 20, 12, 31),
    );
    if (!mounted || selected == null) {
      return;
    }
    setState(() {
      _expiresAt = DateTime.utc(selected.year, selected.month, selected.day);
      _submitFailure = null;
    });
  }

  Future<void> _submit() async {
    if (_isSubmitting) {
      return;
    }
    final ingredient = _selectedIngredient;
    setState(() => _showIngredientError = ingredient == null);
    final isFormValid = _formKey.currentState!.validate();
    if (ingredient == null || !isFormValid) {
      return;
    }
    final quantity = PantryQuantity.fromInput(_quantityController.text);
    setState(() {
      _isSubmitting = true;
      _submitFailure = null;
    });

    try {
      await ref
          .read(pantryRepositoryProvider)
          .addPantryItem(
            ingredientId: ingredient.id,
            quantityG: quantity.value,
            expiresAt: _expiresAt,
          );
      if (!mounted) {
        return;
      }
      ref.invalidate(pantryItemsProvider);
      if (context.canPop()) {
        context.pop();
      } else {
        context.go('/pantry');
      }
    } on PantryFailure catch (failure) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isSubmitting = false;
        _submitFailure = failure;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isSubmitting = false;
        _submitFailure = PantryFailure.createUnexpected();
      });
    }
  }

  void _cancel() {
    if (_isSubmitting) {
      return;
    }
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/pantry');
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_isSubmitting,
      child: Scaffold(
        key: const Key('add-pantry-item-screen'),
        appBar: AppBar(
          title: Text(context.l10n.addIngredient),
          leading: IconButton(
            key: const Key('add-pantry-back-button'),
            onPressed: _isSubmitting ? null : _cancel,
            icon: const Icon(Icons.arrow_back_rounded),
          ),
        ),
        body: SafeArea(
          child: LocalizedForm(
            key: _formKey,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
              children: [
                TextField(
                  key: const Key('ingredient-search-field'),
                  controller: _searchController,
                  enabled: !_isSubmitting,
                  textInputAction: TextInputAction.search,
                  decoration: InputDecoration(
                    labelText: context.l10n.searchIngredients,
                    prefixIcon: Icon(Icons.search),
                  ),
                ),
                const SizedBox(height: 12),
                if (_selectedIngredient != null)
                  Card(
                    key: const Key('selected-ingredient'),
                    color: AppColors.cream,
                    child: ListTile(
                      leading: const Icon(Icons.check_circle_outline),
                      title: Text(_selectedIngredient!.name),
                      subtitle: _selectedIngredient!.category == null
                          ? null
                          : Text(_selectedIngredient!.category!),
                    ),
                  ),
                if (_showIngredientError)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      context.l10n.selectIngredient,
                      key: const Key('ingredient-validation-error'),
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  ),
                SizedBox(height: 240, child: _buildIngredientResults()),
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('pantry-quantity-field'),
                  controller: _quantityController,
                  enabled: !_isSubmitting,
                  validator: (value) =>
                      localizedQuantityError(value, context.l10n),
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  textInputAction: TextInputAction.done,
                  onChanged: (_) {
                    if (_submitFailure != null) {
                      setState(() => _submitFailure = null);
                    }
                  },
                  onFieldSubmitted: (_) => _submit(),
                  decoration: InputDecoration(
                    labelText: context.l10n.quantityLabel,
                    hintText: context.l10n.quantityHint,
                    prefixIcon: Icon(Icons.scale_outlined),
                  ),
                ),
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  key: const Key('pantry-expiry-button'),
                  onPressed: _isSubmitting ? null : _pickExpiry,
                  icon: const Icon(Icons.event_outlined),
                  label: Text(
                    _expiresAt == null
                        ? context.l10n.expiryOptional
                        : _formatDate(_expiresAt!),
                  ),
                ),
                if (_expiresAt != null)
                  TextButton(
                    key: const Key('pantry-expiry-clear-button'),
                    onPressed: _isSubmitting
                        ? null
                        : () => setState(() {
                            _expiresAt = null;
                            _submitFailure = null;
                          }),
                    child: Text(context.l10n.clearExpiry),
                  ),
                if (_submitFailure != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    _submitFailure!.localized(
                      context.l10n,
                      PantryOperation.create,
                    ),
                    key: const Key('add-pantry-error-message'),
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
                const SizedBox(height: 20),
                FilledButton(
                  key: const Key('add-pantry-submit-button'),
                  onPressed: _isSubmitting ? null : _submit,
                  child: _isSubmitting
                      ? const SizedBox(
                          key: Key('add-pantry-loading-indicator'),
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : Text(context.l10n.addToPantry),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildIngredientResults() {
    if (_isSearching) {
      return const Center(
        child: CircularProgressIndicator(
          key: Key('ingredient-search-loading-indicator'),
        ),
      );
    }
    final failure = _searchFailure;
    if (failure != null) {
      return Center(
        key: const Key('ingredient-search-error'),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              failure.localized(context.l10n, PantryOperation.search),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            FilledButton(
              key: const Key('ingredient-search-retry-button'),
              onPressed: () =>
                  _loadIngredients(_lastRequestedQuery ?? '', force: true),
              child: Text(context.l10n.retry),
            ),
          ],
        ),
      );
    }
    if (_ingredients.isEmpty) {
      return Center(
        key: const Key('ingredient-search-empty'),
        child: Text(context.l10n.noIngredients),
      );
    }
    return ListView.builder(
      key: const Key('ingredient-search-results'),
      itemCount: _ingredients.length,
      itemBuilder: (context, index) {
        final ingredient = _ingredients[index];
        return ListTile(
          key: Key('ingredient-result-${ingredient.id}'),
          selected: ingredient == _selectedIngredient,
          title: Text(ingredient.name),
          subtitle: ingredient.category == null
              ? null
              : Text(ingredient.category!),
          onTap: _isSubmitting ? null : () => _selectIngredient(ingredient),
        );
      },
    );
  }
}

String _formatDate(DateTime date) {
  String twoDigits(int value) => value.toString().padLeft(2, '0');
  return '${date.year}-${twoDigits(date.month)}-${twoDigits(date.day)}';
}

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../app/theme/app_colors.dart';
import '../data/pantry_repository.dart';
import '../domain/pantry_failure.dart';
import '../domain/pantry_item.dart';
import '../domain/pantry_quantity.dart';
import 'pantry_providers.dart';

class EditPantryItemScreen extends ConsumerStatefulWidget {
  const EditPantryItemScreen({required this.pantryItem, super.key});

  final PantryItem pantryItem;

  @override
  ConsumerState<EditPantryItemScreen> createState() =>
      _EditPantryItemScreenState();
}

class _EditPantryItemScreenState extends ConsumerState<EditPantryItemScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _quantityController;
  late DateTime? _expiresAt;
  PantryFailure? _failure;
  bool _isMutating = false;
  bool _isDeleteConfirmationOpen = false;

  @override
  void initState() {
    super.initState();
    _quantityController = TextEditingController(
      text: _formatQuantityInput(widget.pantryItem.quantityG),
    );
    _expiresAt = widget.pantryItem.expiresAt;
  }

  @override
  void dispose() {
    _quantityController.dispose();
    super.dispose();
  }

  Future<void> _pickExpiry() async {
    if (_isInteractionLocked) {
      return;
    }
    final now = DateTime.now();
    final currentExpiry = _expiresAt;
    final initialDate = currentExpiry == null
        ? now
        : _calendarDate(currentExpiry);
    final defaultFirstDate = DateTime(now.year - 10);
    final defaultLastDate = DateTime(now.year + 20, 12, 31);
    final selected = await showDatePicker(
      context: context,
      initialDate: initialDate,
      firstDate: initialDate.isBefore(defaultFirstDate)
          ? initialDate
          : defaultFirstDate,
      lastDate: initialDate.isAfter(defaultLastDate)
          ? initialDate
          : defaultLastDate,
    );
    if (!mounted || selected == null) {
      return;
    }
    setState(() {
      _expiresAt = DateTime.utc(selected.year, selected.month, selected.day);
      _failure = null;
    });
  }

  Future<void> _save() async {
    if (_isInteractionLocked || !_formKey.currentState!.validate()) {
      return;
    }
    final quantity = PantryQuantity.fromInput(_quantityController.text);
    setState(() {
      _isMutating = true;
      _failure = null;
    });

    try {
      await ref
          .read(pantryRepositoryProvider)
          .updatePantryItem(
            pantryItemId: widget.pantryItem.id,
            quantityG: quantity.value,
            expiresAt: _expiresAt,
          );
      if (!mounted) {
        return;
      }
      ref.invalidate(pantryItemsProvider);
      _returnToPantry();
    } on PantryFailure catch (failure) {
      _showFailure(failure);
    } catch (_) {
      _showFailure(PantryFailure.updateUnexpected());
    }
  }

  Future<void> _confirmDelete() async {
    if (_isInteractionLocked) {
      return;
    }
    setState(() {
      _isDeleteConfirmationOpen = true;
      _failure = null;
    });
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        var isConfirming = false;
        return StatefulBuilder(
          builder: (context, setDialogState) => AlertDialog(
            key: const Key('edit-pantry-delete-confirm-dialog'),
            title: const Text('Delete pantry item?'),
            content: Text(
              'Remove ${widget.pantryItem.ingredient.name} from your pantry?',
            ),
            actions: [
              TextButton(
                key: const Key('edit-pantry-delete-cancel-button'),
                onPressed: isConfirming
                    ? null
                    : () => Navigator.of(dialogContext).pop(false),
                child: const Text('Cancel'),
              ),
              FilledButton(
                key: const Key('edit-pantry-delete-confirm-button'),
                onPressed: isConfirming
                    ? null
                    : () {
                        if (isConfirming) {
                          return;
                        }
                        setDialogState(() => isConfirming = true);
                        Navigator.of(dialogContext).pop(true);
                      },
                child: const Text('Delete'),
              ),
            ],
          ),
        );
      },
    );
    if (!mounted) {
      return;
    }
    setState(() => _isDeleteConfirmationOpen = false);
    if (confirmed != true) {
      return;
    }
    await _delete();
  }

  Future<void> _delete() async {
    if (_isMutating) {
      return;
    }
    setState(() {
      _isMutating = true;
      _failure = null;
    });
    try {
      await ref
          .read(pantryRepositoryProvider)
          .deletePantryItem(pantryItemId: widget.pantryItem.id);
      if (!mounted) {
        return;
      }
      ref.invalidate(pantryItemsProvider);
      _returnToPantry();
    } on PantryFailure catch (failure) {
      _showFailure(failure);
    } catch (_) {
      _showFailure(PantryFailure.deleteUnexpected());
    }
  }

  void _showFailure(PantryFailure failure) {
    if (!mounted) {
      return;
    }
    setState(() {
      _isMutating = false;
      _failure = failure;
    });
  }

  void _returnToPantry() {
    context.go('/pantry');
  }

  void _cancel() {
    if (_isInteractionLocked) {
      return;
    }
    if (context.canPop()) {
      context.pop();
    } else {
      context.go('/pantry');
    }
  }

  bool get _isInteractionLocked => _isMutating || _isDeleteConfirmationOpen;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_isInteractionLocked,
      child: Scaffold(
        key: const Key('edit-pantry-item-screen'),
        appBar: AppBar(
          title: const Text('Edit ingredient'),
          leading: IconButton(
            key: const Key('edit-pantry-back-button'),
            onPressed: _isInteractionLocked ? null : _cancel,
            icon: const Icon(Icons.arrow_back_rounded),
          ),
        ),
        body: SafeArea(
          child: Form(
            key: _formKey,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
              children: [
                Card(
                  key: const Key('edit-pantry-ingredient'),
                  color: AppColors.cream,
                  child: ListTile(
                    leading: const Icon(Icons.kitchen_outlined),
                    title: Text(widget.pantryItem.ingredient.name),
                    subtitle: widget.pantryItem.ingredient.category == null
                        ? null
                        : Text(widget.pantryItem.ingredient.category!),
                  ),
                ),
                const SizedBox(height: 16),
                TextFormField(
                  key: const Key('edit-pantry-quantity-field'),
                  controller: _quantityController,
                  enabled: !_isInteractionLocked,
                  validator: PantryQuantity.validate,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  textInputAction: TextInputAction.done,
                  onChanged: (_) {
                    if (_failure != null) {
                      setState(() => _failure = null);
                    }
                  },
                  onFieldSubmitted: (_) => _save(),
                  decoration: const InputDecoration(
                    labelText: 'Quantity (g)',
                    hintText: '500.25',
                    prefixIcon: Icon(Icons.scale_outlined),
                  ),
                ),
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  key: const Key('edit-pantry-expiry-button'),
                  onPressed: _isInteractionLocked ? null : _pickExpiry,
                  icon: const Icon(Icons.event_outlined),
                  label: Text(
                    _expiresAt == null
                        ? 'Expiration date (optional)'
                        : _formatDate(_expiresAt!),
                  ),
                ),
                if (_expiresAt != null)
                  TextButton(
                    key: const Key('edit-pantry-expiry-clear-button'),
                    onPressed: _isInteractionLocked
                        ? null
                        : () => setState(() {
                            _expiresAt = null;
                            _failure = null;
                          }),
                    child: const Text('Clear expiration date'),
                  ),
                if (_failure != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    _failure!.message,
                    key: const Key('edit-pantry-error-message'),
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.error,
                    ),
                  ),
                ],
                const SizedBox(height: 20),
                FilledButton(
                  key: const Key('edit-pantry-save-button'),
                  onPressed: _isInteractionLocked ? null : _save,
                  child: _isMutating
                      ? const SizedBox(
                          key: Key('edit-pantry-loading-indicator'),
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Save changes'),
                ),
                const SizedBox(height: 12),
                TextButton.icon(
                  key: const Key('edit-pantry-delete-button'),
                  onPressed: _isInteractionLocked ? null : _confirmDelete,
                  icon: const Icon(Icons.delete_outline),
                  label: const Text('Delete from pantry'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

String _formatQuantityInput(double quantity) {
  final value = quantity.toString();
  return value.contains('.')
      ? value.replaceFirst(RegExp(r'0+$'), '').replaceFirst(RegExp(r'\.$'), '')
      : value;
}

String _formatDate(DateTime date) {
  final utcDate = date.toUtc();
  return '${utcDate.year.toString().padLeft(4, '0')}-'
      '${utcDate.month.toString().padLeft(2, '0')}-'
      '${utcDate.day.toString().padLeft(2, '0')}';
}

DateTime _calendarDate(DateTime date) {
  final utcDate = date.toUtc();
  return DateTime(utcDate.year, utcDate.month, utcDate.day);
}

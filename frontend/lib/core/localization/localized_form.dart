import 'package:flutter/widgets.dart';

/// Re-translates submitted validation errors without replacing fields or inputs.
class LocalizedForm extends Form {
  const LocalizedForm({required super.child, super.key});

  @override
  FormState createState() => _LocalizedFormState();
}

class _LocalizedFormState extends FormState {
  Locale? _locale;
  bool _wasValidated = false;

  @override
  bool validate() {
    _wasValidated = true;
    return super.validate();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final locale = Localizations.localeOf(context);
    if (_locale != null && _locale != locale && _wasValidated) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) validate();
      });
    }
    _locale = locale;
  }
}

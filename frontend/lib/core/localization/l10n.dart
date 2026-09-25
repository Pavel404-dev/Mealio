import 'package:flutter/widgets.dart';

import '../../features/auth/domain/auth_failure.dart';
import '../../features/pantry/domain/pantry_failure.dart';
import '../../features/pantry/domain/pantry_quantity.dart';
import '../../l10n/generated/app_localizations.dart';

export 'localized_form.dart';

extension LocalizationContext on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
}

extension LocalizedAuthFailure on AuthFailure {
  String localized(AppLocalizations l10n) => switch (type) {
    AuthFailureType.invalidCredentials => l10n.authInvalidCredentials,
    AuthFailureType.validation => l10n.authValidation,
    AuthFailureType.duplicateEmail => l10n.authDuplicateEmail,
    AuthFailureType.registrationValidation => l10n.authRegistrationValidation,
    AuthFailureType.emailVerificationInvalid =>
      l10n.authEmailVerificationInvalid,
    AuthFailureType.emailVerificationRequest =>
      l10n.authEmailVerificationRequest,
    AuthFailureType.emailVerificationOtpRequest =>
      l10n.authEmailVerificationOtpRequest,
    AuthFailureType.emailVerificationOtpInvalid =>
      l10n.authEmailVerificationOtpInvalid,
    AuthFailureType.rateLimited => l10n.rateLimited,
    AuthFailureType.passwordResetRequest => l10n.authPasswordResetRequest,
    AuthFailureType.passwordResetInvalid => l10n.authPasswordResetInvalid,
    AuthFailureType.passwordResetValidation => l10n.authPasswordResetValidation,
    AuthFailureType.passwordResetPasswordReuse =>
      l10n.authPasswordResetPasswordReuse,
    AuthFailureType.passwordResetOtpRequest => l10n.authPasswordResetOtpRequest,
    AuthFailureType.passwordResetOtpInvalid => l10n.authPasswordResetOtpInvalid,
    AuthFailureType.passwordResetOtpValidation =>
      l10n.authPasswordResetOtpValidation,
    AuthFailureType.connection => l10n.connectionError,
    AuthFailureType.invalidSession ||
    AuthFailureType.unexpected => l10n.unexpectedError,
  };
}

/// Presentation context: repository failure types and legacy messages stay stable.
enum PantryOperation { list, search, create, update, delete }

extension LocalizedPantryFailure on PantryFailure {
  String localized(AppLocalizations l10n, PantryOperation operation) =>
      switch (type) {
        PantryFailureType.connection => l10n.connectionError,
        PantryFailureType.duplicate => l10n.pantryDuplicate,
        PantryFailureType.ingredientUnavailable => l10n.ingredientUnavailable,
        PantryFailureType.pantryItemUnavailable => l10n.pantryItemUnavailable,
        PantryFailureType.validation => l10n.pantryValidation,
        PantryFailureType.authentication => l10n.pantryAuthentication,
        PantryFailureType.backend ||
        PantryFailureType.unexpected => switch (operation) {
          PantryOperation.list => l10n.pantryLoadError,
          PantryOperation.search => l10n.pantrySearchError,
          PantryOperation.create => l10n.pantryCreateError,
          PantryOperation.update => l10n.pantryUpdateError,
          PantryOperation.delete => l10n.pantryDeleteError,
        },
      };
}

String? localizedQuantityError(String? value, AppLocalizations l10n) =>
    switch (PantryQuantity.validationError(value)) {
      null => null,
      PantryQuantityError.required => l10n.quantityRequired,
      PantryQuantityError.invalid => l10n.quantityInvalid,
      PantryQuantityError.nonPositive => l10n.quantityPositive,
    };

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mealio/core/localization/l10n.dart';
import 'package:mealio/features/auth/domain/auth_failure.dart';
import 'package:mealio/features/pantry/domain/pantry_failure.dart';
import 'package:mealio/l10n/generated/app_localizations.dart';

void main() {
  for (final code in ['en', 'ru', 'uk', 'sk']) {
    test('$code maps all failures without exposing raw messages', () async {
      final l10n = await AppLocalizations.delegate.load(Locale(code));
      const privateDetail = 'synthetic-private-detail';
      for (final type in AuthFailureType.values) {
        final message = AuthFailure(
          type: type,
          message: privateDetail,
        ).localized(l10n);
        expect(message, isNotEmpty);
        expect(message, isNot(contains(privateDetail)));
      }
      for (final type in PantryFailureType.values) {
        for (final operation in PantryOperation.values) {
          final message = PantryFailure(
            type: type,
            message: privateDetail,
          ).localized(l10n, operation);
          expect(message, isNotEmpty);
          expect(message, isNot(contains(privateDetail)));
        }
      }
      for (final type in [
        PantryFailureType.backend,
        PantryFailureType.unexpected,
      ]) {
        final failure = PantryFailure(type: type, message: privateDetail);
        final messages = [
          for (final operation in PantryOperation.values)
            failure.localized(l10n, operation),
        ];
        expect(messages, [
          l10n.pantryLoadError,
          l10n.pantrySearchError,
          l10n.pantryCreateError,
          l10n.pantryUpdateError,
          l10n.pantryDeleteError,
        ]);
        expect(messages.toSet(), hasLength(5));
      }
      expect(
        AuthFailure.passwordResetPasswordReuse().localized(l10n),
        l10n.authPasswordResetPasswordReuse,
      );
      expect(AuthFailure.rateLimited().localized(l10n), l10n.rateLimited);
      expect(localizedQuantityError('0', l10n), l10n.quantityPositive);
      expect(localizedQuantityError('', l10n), l10n.quantityRequired);
      expect(localizedQuantityError('1.123', l10n), l10n.quantityInvalid);
      expect(localizedQuantityError('1,25', l10n), isNull);
    });

    test(
      '$code interpolation preserves server names and fixed units/dates',
      () async {
        final l10n = await AppLocalizations.delegate.load(Locale(code));
        const name = 'Server ingredient {name}';
        expect(l10n.greetingNamed(name), contains(name));
        expect(l10n.deletePantryConfirmation(name), contains(name));
        expect(
          l10n.quantityWithExpiry('12.25', '2026-09-30'),
          contains('12.25'),
        );
        expect(
          l10n.quantityWithExpiry('12.25', '2026-09-30'),
          contains('2026-09-30'),
        );
      },
    );
  }

  test(
    'plural forms are generated for English, Russian, Ukrainian and Slovak',
    () async {
      final en = await AppLocalizations.delegate.load(const Locale('en'));
      final ru = await AppLocalizations.delegate.load(const Locale('ru'));
      final uk = await AppLocalizations.delegate.load(const Locale('uk'));
      final sk = await AppLocalizations.delegate.load(const Locale('sk'));
      expect(en.passwordMinimum(1), 'Password must be at least 1 character.');
      expect(
        en.passwordMinimum(15),
        'Password must be at least 15 characters.',
      );
      expect(ru.passwordMinimum(21), contains('21 символа'));
      expect(ru.passwordMinimum(15), contains('15 символов'));
      expect(uk.passwordMinimum(1), contains('1 символ'));
      expect(uk.passwordMinimum(2), contains('2 символи'));
      expect(uk.passwordMinimum(15), contains('15 символів'));
      expect(sk.passwordMinimum(1), contains('1 znak'));
      expect(sk.passwordMinimum(2), contains('2 znaky'));
      expect(sk.passwordMinimum(15), contains('15 znakov'));
    },
  );
}

import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../l10n/generated/app_localizations.dart';
import '../storage/secure_storage_provider.dart';

const localeStorageKey = 'mealio_locale_override';

final localeStorageProvider = Provider<LocaleStorage>(
  (ref) => LocaleStorage(ref.watch(flutterSecureStorageProvider)),
);

/// Own key and operations; token cleanup never reads or deletes this preference.
class LocaleStorage {
  LocaleStorage(this._storage);
  final FlutterSecureStorage _storage;

  Future<String?> read() => _storage.read(key: localeStorageKey);
  Future<void> write(String? languageCode) => languageCode == null
      ? _storage.delete(key: localeStorageKey)
      : _storage.write(key: localeStorageKey, value: languageCode);
}

final localeControllerProvider = NotifierProvider<LocaleController, Locale?>(
  LocaleController.new,
);

class LocaleController extends Notifier<Locale?> {
  late LocaleStorage _storage;
  late Future<void> restored;
  Future<void> _writeTail = Future<void>.value();
  int _revision = 0;

  @override
  Locale? build() {
    _storage = ref.read(localeStorageProvider);
    restored = _restore();
    return null;
  }

  Future<void> _restore() async {
    final revision = _revision;
    try {
      final code = await _storage.read();
      if (ref.mounted && revision == _revision) {
        state = _supportedLocale(code);
      }
    } catch (_) {
      // Unavailable or corrupt storage must not prevent startup or sign-in.
    }
  }

  /// Applies immediately; serial writes preserve the last choice across restart.
  /// False means this choice is only available for the current session.
  Future<bool> setLocale(Locale? locale) {
    final selected = _supportedLocale(locale?.languageCode);
    if (locale != null && selected == null) {
      throw ArgumentError('Unsupported application locale');
    }
    _revision++;
    state = selected;
    final completion = Completer<bool>();
    _writeTail = _writeTail.then((_) async {
      try {
        await _storage.write(selected?.languageCode);
        completion.complete(true);
      } catch (_) {
        completion.complete(false);
      }
    });
    return completion.future;
  }

  Locale? _supportedLocale(String? code) {
    for (final locale in AppLocalizations.supportedLocales) {
      if (locale.languageCode == code) return locale;
    }
    return null;
  }
}

/// Language preference order is authoritative; region never selects a language.
Locale resolveAppLocale(
  List<Locale>? preferredLocales,
  Iterable<Locale> supportedLocales,
) {
  for (final preferred in preferredLocales ?? const <Locale>[]) {
    for (final supported in supportedLocales) {
      if (preferred.languageCode == supported.languageCode) return supported;
    }
  }
  return const Locale('en');
}

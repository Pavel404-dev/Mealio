import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'l10n.dart';
import 'locale_controller.dart';

class LanguageButton extends ConsumerWidget {
  const LanguageButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selectedLanguageCode = Localizations.localeOf(context).languageCode;
    return PopupMenuButton<String>(
      key: const Key('language-button'),
      tooltip: context.l10n.language,
      initialValue: selectedLanguageCode,
      icon: const Icon(Icons.language),
      itemBuilder: (context) => [
        for (final entry in {
          'en': context.l10n.languageEnglish,
          'ru': context.l10n.languageRussian,
          'uk': context.l10n.languageUkrainian,
          'sk': context.l10n.languageSlovak,
        }.entries)
          CheckedPopupMenuItem(
            value: entry.key,
            checked: selectedLanguageCode == entry.key,
            child: Text(entry.value),
          ),
      ],
      onSelected: (code) async {
        final saved = await ref
            .read(localeControllerProvider.notifier)
            .setLocale(Locale(code));
        if (!saved && context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Builder(
                builder: (context) => Text(context.l10n.languageSaveFailed),
              ),
            ),
          );
        }
      },
    );
  }
}

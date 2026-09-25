import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import '../../../tool/check_l10n.dart';

void main() {
  late Map<String, Map<String, dynamic>> catalogs;
  setUp(() {
    catalogs = {
      for (final language in languages)
        language:
            jsonDecode(File('lib/l10n/app_$language.arb').readAsStringSync())
                as Map<String, dynamic>,
    };
  });

  test('all shipped catalogs have complete keys and typed ICU arguments', () {
    expect(validateCatalogs(catalogs), isEmpty);
  });

  test('missing translations cannot silently fall back to English', () {
    catalogs['uk']!.remove('login');
    expect(validateCatalogs(catalogs), contains('uk: missing login'));
  });

  test('extra keys and blank translations are rejected', () {
    catalogs['sk']!['obsolete'] = 'old';
    catalogs['ru']!['login'] = '  ';
    expect(validateCatalogs(catalogs), contains('sk: unknown obsolete'));
    expect(
      validateCatalogs(catalogs),
      contains('ru/login: empty or non-string translation'),
    );
  });

  test('renamed arguments and changed types fail the check', () {
    catalogs['ru']!['greetingNamed'] = 'Привет, {person}';
    catalogs['sk']!['@passwordMinimum']['placeholders']['count']['type'] =
        'String';
    final errors = validateCatalogs(catalogs);
    expect(
      errors,
      contains('ru/greetingNamed: message and placeholder metadata differ'),
    );
    expect(
      errors,
      contains('sk/passwordMinimum/count: placeholder contract differs'),
    );
  });

  test('malformed ICU and missing other plural branch are rejected', () {
    catalogs['ru']!['passwordMinimum'] = '{count, plural, one{символ}}';
    catalogs['uk']!['greetingNamed'] = 'Привіт, {name';
    expect(
      validateCatalogs(catalogs),
      contains('ru/passwordMinimum: invalid ICU message'),
    );
    expect(
      validateCatalogs(catalogs),
      contains('uk/greetingNamed: invalid ICU message'),
    );
  });
}

import 'dart:convert';
import 'dart:io';

const languages = ['en', 'ru', 'uk', 'sk'];

/// Checks complete translations and explicit, identical placeholder contracts.
/// gen_l10n remains the authoritative ICU syntax/type/code-generation check.
List<String> validateCatalogs(Map<String, Map<String, dynamic>> catalogs) {
  final errors = <String>[];
  final template = catalogs['en'];
  if (template == null) return ['Missing English template'];
  Set<String> keys(Map<String, dynamic> arb) =>
      arb.keys.where((key) => !key.startsWith('@')).toSet();
  final expected = keys(template);
  for (final language in languages) {
    final arb = catalogs[language];
    if (arb == null) {
      errors.add('Missing catalog: $language');
      continue;
    }
    if (arb['@@locale'] != language) {
      errors.add('$language: incorrect @@locale');
    }
    final actual = keys(arb);
    for (final key in expected.difference(actual)) {
      errors.add('$language: missing $key');
    }
    for (final key in actual.difference(expected)) {
      errors.add('$language: unknown $key');
    }
    for (final key in actual) {
      final message = arb[key];
      if (message is! String || message.trim().isEmpty) {
        errors.add('$language/$key: empty or non-string translation');
        continue;
      }
      try {
        final used = _MessageParameters(message).parse();
        final metadata = arb['@$key'];
        final declared = metadata is Map
            ? metadata['placeholders'] as Map? ?? {}
            : {};
        if (used.length != declared.length ||
            !used.containsAll(declared.keys.cast<String>())) {
          errors.add('$language/$key: message and placeholder metadata differ');
        }
        final baseMetadata = template['@$key'];
        final base = baseMetadata is Map
            ? baseMetadata['placeholders'] as Map? ?? {}
            : {};
        if (declared.length != base.length ||
            !declared.keys.toSet().containsAll(base.keys)) {
          errors.add('$language/$key: placeholder keys differ from English');
        }
        for (final parameter in declared.keys) {
          final definition = declared[parameter];
          if (definition is! Map ||
              ![
                'String',
                'int',
                'double',
                'num',
                'DateTime',
              ].contains(definition['type'])) {
            errors.add(
              '$language/$key/$parameter: explicit supported type required',
            );
          } else if (jsonEncode(definition) != jsonEncode(base[parameter])) {
            errors.add(
              '$language/$key/$parameter: placeholder contract differs',
            );
          }
        }
      } on FormatException {
        errors.add('$language/$key: invalid ICU message');
      } on TypeError {
        errors.add('$language/$key: invalid placeholder metadata');
      }
    }
    for (final key in arb.keys.where(
      (key) => key.startsWith('@') && !key.startsWith('@@'),
    )) {
      if (!actual.contains(key.substring(1))) {
        errors.add('$language: orphan metadata $key');
      }
    }
  }
  return errors;
}

/// Parses arguments recursively, distinguishing plural option bodies from
/// arguments. Apostrophes are literal (matching l10n.yaml's default escaping).
class _MessageParameters {
  _MessageParameters(this.text);
  final String text;
  int offset = 0;
  final Set<String> parameters = {};

  Set<String> parse() {
    _message(nested: false);
    return parameters;
  }

  Never _invalid() => throw const FormatException('Invalid ICU structure');

  void _space() {
    while (offset < text.length && text[offset].trim().isEmpty) {
      offset++;
    }
  }

  String _until(Set<String> delimiters) {
    final start = offset;
    while (offset < text.length && !delimiters.contains(text[offset])) {
      offset++;
    }
    return text.substring(start, offset).trim();
  }

  void _message({required bool nested}) {
    while (offset < text.length) {
      if (text[offset] == '}') {
        if (!nested) _invalid();
        offset++;
        return;
      }
      if (text[offset++] != '{') continue;
      final name = _until({',', '}'});
      if (!RegExp(r'^[a-zA-Z]\w*$').hasMatch(name) || offset == text.length) {
        _invalid();
      }
      parameters.add(name);
      if (text[offset++] == '}') continue;
      final kind = _until({','});
      if (!['plural', 'select', 'selectordinal'].contains(kind) ||
          offset == text.length) {
        _invalid();
      }
      offset++;
      final options = <String>{};
      while (true) {
        _space();
        if (offset == text.length) _invalid();
        if (text[offset] == '}') {
          offset++;
          break;
        }
        final option = _until({'{'});
        if (option.isEmpty || offset == text.length || !options.add(option)) {
          _invalid();
        }
        offset++;
        _message(nested: true);
      }
      if (!options.contains('other')) _invalid();
    }
    if (nested) _invalid();
  }
}

void main(List<String> args) {
  final directory = args.isEmpty ? 'lib/l10n' : args.single;
  final catalogs = <String, Map<String, dynamic>>{};
  try {
    for (final language in languages) {
      final file = File('$directory/app_$language.arb');
      if (file.existsSync()) {
        catalogs[language] =
            jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
      }
    }
    final errors = validateCatalogs(catalogs);
    if (errors.isNotEmpty) {
      stderr.writeln(errors.join('\n'));
      exitCode = 1;
      return;
    }
    stdout.writeln(
      'ARB check passed: en, ru, uk, sk; complete keys and typed parameters.',
    );
  } on Object {
    stderr.writeln('Unable to parse ARB catalogs.');
    exitCode = 1;
  }
}

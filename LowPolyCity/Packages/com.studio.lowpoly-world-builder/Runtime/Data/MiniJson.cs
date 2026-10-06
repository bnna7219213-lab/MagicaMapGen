using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace LowPolyWorldBuilder.Data
{
    /// <summary>Raised when a map document cannot be decoded. Carries a JSON-ish path.</summary>
    public sealed class MapDecodeException : Exception
    {
        public string Path { get; }

        public MapDecodeException(string path, string message) : base(message)
        {
            Path = path;
        }

        public override string ToString() => string.IsNullOrEmpty(Path) ? Message : $"{Path}: {Message}";
    }

    /// <summary>
    /// Minimal, allocation-conscious JSON reader.
    ///
    /// Unity's JsonUtility cannot represent the RLE grids in map.json: they are
    /// jagged arrays ([[value, run], ...]) and JsonUtility supports neither
    /// jagged arrays nor dictionaries. The project also has no Newtonsoft
    /// dependency, and a prototype tool should not take one just to read its own
    /// primary deliverable. So this parses into plain CLR types
    /// (Dictionary&lt;string, object&gt; / List&lt;object&gt; / double / string / bool / null)
    /// and the decoder walks that with strict, path-qualified errors.
    ///
    /// Strict by design: malformed input throws with an offset rather than being
    /// silently repaired, matching the generator's "fail loud" contract layer.
    /// </summary>
    public static class MiniJson
    {
        public static object Parse(string text)
        {
            if (text == null) throw new MapDecodeException("", "JSON text is null");
            int i = 0;
            var value = ParseValue(text, ref i, 0);
            SkipWhitespace(text, ref i);
            if (i != text.Length)
                throw Error(text, i, "trailing content after top-level value");
            return value;
        }

        const int MaxDepth = 64;

        static object ParseValue(string s, ref int i, int depth)
        {
            if (depth > MaxDepth) throw Error(s, i, "nesting too deep");
            SkipWhitespace(s, ref i);
            if (i >= s.Length) throw Error(s, i, "unexpected end of input");
            char c = s[i];
            switch (c)
            {
                case '{': return ParseObject(s, ref i, depth);
                case '[': return ParseArray(s, ref i, depth);
                case '"': return ParseString(s, ref i);
                case 't': Expect(s, ref i, "true"); return true;
                case 'f': Expect(s, ref i, "false"); return false;
                case 'n': Expect(s, ref i, "null"); return null;
                default: return ParseNumber(s, ref i);
            }
        }

        static Dictionary<string, object> ParseObject(string s, ref int i, int depth)
        {
            var map = new Dictionary<string, object>(StringComparer.Ordinal);
            i++; // '{'
            SkipWhitespace(s, ref i);
            if (i < s.Length && s[i] == '}') { i++; return map; }
            while (true)
            {
                SkipWhitespace(s, ref i);
                if (i >= s.Length || s[i] != '"') throw Error(s, i, "expected object key string");
                string key = ParseString(s, ref i);
                SkipWhitespace(s, ref i);
                if (i >= s.Length || s[i] != ':') throw Error(s, i, "expected ':' after object key");
                i++;
                map[key] = ParseValue(s, ref i, depth + 1);
                SkipWhitespace(s, ref i);
                if (i >= s.Length) throw Error(s, i, "unterminated object");
                if (s[i] == ',') { i++; continue; }
                if (s[i] == '}') { i++; return map; }
                throw Error(s, i, "expected ',' or '}' in object");
            }
        }

        static List<object> ParseArray(string s, ref int i, int depth)
        {
            var list = new List<object>();
            i++; // '['
            SkipWhitespace(s, ref i);
            if (i < s.Length && s[i] == ']') { i++; return list; }
            while (true)
            {
                list.Add(ParseValue(s, ref i, depth + 1));
                SkipWhitespace(s, ref i);
                if (i >= s.Length) throw Error(s, i, "unterminated array");
                if (s[i] == ',') { i++; continue; }
                if (s[i] == ']') { i++; return list; }
                throw Error(s, i, "expected ',' or ']' in array");
            }
        }

        static string ParseString(string s, ref int i)
        {
            i++; // opening quote
            var sb = new StringBuilder();
            while (true)
            {
                if (i >= s.Length) throw Error(s, i, "unterminated string");
                char c = s[i++];
                if (c == '"') return sb.ToString();
                if (c != '\\') { sb.Append(c); continue; }
                if (i >= s.Length) throw Error(s, i, "unterminated escape");
                char e = s[i++];
                switch (e)
                {
                    case '"': sb.Append('"'); break;
                    case '\\': sb.Append('\\'); break;
                    case '/': sb.Append('/'); break;
                    case 'b': sb.Append('\b'); break;
                    case 'f': sb.Append('\f'); break;
                    case 'n': sb.Append('\n'); break;
                    case 'r': sb.Append('\r'); break;
                    case 't': sb.Append('\t'); break;
                    case 'u':
                        if (i + 4 > s.Length) throw Error(s, i, "truncated \\u escape");
                        if (!ushort.TryParse(s.Substring(i, 4), NumberStyles.HexNumber,
                                CultureInfo.InvariantCulture, out ushort code))
                            throw Error(s, i, "invalid \\u escape");
                        sb.Append((char)code);
                        i += 4;
                        break;
                    default: throw Error(s, i - 1, $"invalid escape '\\{e}'");
                }
            }
        }

        static object ParseNumber(string s, ref int i)
        {
            int start = i;
            if (i < s.Length && (s[i] == '-' || s[i] == '+')) i++;
            while (i < s.Length)
            {
                char c = s[i];
                if ((c >= '0' && c <= '9') || c == '.' || c == 'e' || c == 'E' || c == '+' || c == '-')
                    i++;
                else
                    break;
            }
            if (start == i) throw Error(s, i, "expected a value");
            string slice = s.Substring(start, i - start);
            if (!double.TryParse(slice, NumberStyles.Float, CultureInfo.InvariantCulture, out double d))
                throw Error(s, start, $"invalid number '{slice}'");
            return d;
        }

        static void Expect(string s, ref int i, string literal)
        {
            if (i + literal.Length > s.Length || string.CompareOrdinal(s, i, literal, 0, literal.Length) != 0)
                throw Error(s, i, $"expected '{literal}'");
            i += literal.Length;
        }

        static void SkipWhitespace(string s, ref int i)
        {
            while (i < s.Length)
            {
                char c = s[i];
                if (c == ' ' || c == '\t' || c == '\n' || c == '\r') i++;
                else break;
            }
        }

        static MapDecodeException Error(string s, int i, string message)
        {
            // Report a 1-based offset and the offending line for log readability.
            int line = 1;
            int lineStart = 0;
            for (int k = 0; k < i && k < s.Length; k++)
            {
                if (s[k] == '\n') { line++; lineStart = k + 1; }
            }
            int col = i - lineStart + 1;
            string snippet = s.Substring(lineStart, Math.Min(60, Math.Max(0, s.Length - lineStart)))
                                 .Replace("\n", "\\n").Replace("\r", "");
            return new MapDecodeException("", $"{message} (line {line}, col {col}, offset {i}): ...{snippet}...");
        }
    }
}

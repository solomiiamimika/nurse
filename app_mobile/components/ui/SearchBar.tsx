import { View, TextInput, StyleSheet } from 'react-native';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useThemeColor } from '@/hooks/use-theme-color';
import { useRef, useCallback } from 'react';

interface SearchBarProps {
  value: string;
  onChangeText: (text: string) => void;
  placeholder?: string;
  debounceMs?: number;
}

export function SearchBar({ value, onChangeText, placeholder = 'Search...', debounceMs = 300 }: SearchBarProps) {
  const bg = useThemeColor({}, 'card');
  const border = useThemeColor({}, 'cardBorder');
  const text = useThemeColor({}, 'text');
  const muted = useThemeColor({}, 'muted');

  const timer = useRef<ReturnType<typeof setTimeout>>();

  const handleChange = useCallback((t: string) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => onChangeText(t), debounceMs);
  }, [onChangeText, debounceMs]);

  return (
    <View style={[styles.container, { backgroundColor: bg, borderColor: border }]}>
      <MaterialIcons name="search" size={20} color={muted} />
      <TextInput
        style={[styles.input, { color: text }]}
        placeholder={placeholder}
        placeholderTextColor={muted}
        defaultValue={value}
        onChangeText={handleChange}
        autoCapitalize="none"
        autoCorrect={false}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 12,
    height: 44,
    gap: 8,
  },
  input: { flex: 1, fontSize: 16 },
});

import { View, Image, Text, StyleSheet } from 'react-native';
import { useThemeColor } from '@/hooks/use-theme-color';

interface AvatarProps {
  uri?: string | null;
  name?: string;
  size?: number;
  online?: boolean;
}

export function Avatar({ uri, name, size = 48, online }: AvatarProps) {
  const primary = useThemeColor({}, 'primary');
  const success = useThemeColor({}, 'success');

  const initials = name
    ? name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : '?';

  return (
    <View style={{ width: size, height: size }}>
      {uri ? (
        <Image source={{ uri }} style={[styles.image, { width: size, height: size, borderRadius: size / 2 }]} />
      ) : (
        <View style={[styles.fallback, { width: size, height: size, borderRadius: size / 2, backgroundColor: primary }]}>
          <Text style={[styles.initials, { fontSize: size * 0.38 }]}>{initials}</Text>
        </View>
      )}
      {online !== undefined && (
        <View style={[styles.dot, {
          backgroundColor: online ? success : '#9ca3af',
          width: size * 0.28,
          height: size * 0.28,
          borderRadius: size * 0.14,
          right: 0,
          bottom: 0,
        }]} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  image: { resizeMode: 'cover' },
  fallback: { justifyContent: 'center', alignItems: 'center' },
  initials: { color: '#fff', fontWeight: '700' },
  dot: { position: 'absolute', borderWidth: 2, borderColor: '#fff' },
});

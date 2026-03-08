import { View, TouchableOpacity, StyleSheet } from 'react-native';
import MaterialIcons from '@expo/vector-icons/MaterialIcons';

interface StarRatingProps {
  rating: number;
  size?: number;
  color?: string;
  interactive?: boolean;
  onRate?: (rating: number) => void;
}

export function StarRating({ rating, size = 16, color = '#f59e0b', interactive = false, onRate }: StarRatingProps) {
  return (
    <View style={styles.row}>
      {[1, 2, 3, 4, 5].map(i => {
        const name = i <= Math.round(rating) ? 'star' : 'star-border';
        if (interactive) {
          return (
            <TouchableOpacity key={i} onPress={() => onRate?.(i)}>
              <MaterialIcons name={name} size={size} color={color} />
            </TouchableOpacity>
          );
        }
        return <MaterialIcons key={i} name={name} size={size} color={color} />;
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 2 },
});

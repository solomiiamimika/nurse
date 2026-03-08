import React, { useState, useEffect, useRef } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
} from 'react-native';
import { useRouter, Stack } from 'expo-router';
import MapView, { Marker, Callout } from 'react-native-maps';
import * as Location from 'expo-location';
import { useAuth } from '@/contexts/AuthContext';
import api from '../src/api/api';

interface MapMarker {
  id: number;
  name: string;
  lat: number;
  lng: number;
  online?: boolean;
}

const DEFAULT_REGION = {
  latitude: 50.4,
  longitude: 30.5,
  latitudeDelta: 0.1,
  longitudeDelta: 0.1,
};

export default function MapScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const mapRef = useRef<MapView>(null);

  const [markers, setMarkers] = useState<MapMarker[]>([]);
  const [loading, setLoading] = useState(true);
  const [region, setRegion] = useState(DEFAULT_REGION);

  const isProvider = user?.role === 'provider';

  useEffect(() => {
    getUserLocation();
    fetchLocations();
  }, []);

  const getUserLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') return;
      const loc = await Location.getCurrentPositionAsync({});
      const coords = {
        latitude: loc.coords.latitude,
        longitude: loc.coords.longitude,
      };
      setRegion({
        ...coords,
        latitudeDelta: 0.05,
        longitudeDelta: 0.05,
      });
    } catch (err) {
      console.error('Failed to get location:', err);
    }
  };

  const fetchLocations = async () => {
    setLoading(true);
    try {
      const endpoint = isProvider
        ? '/provider/get_clients_locations'
        : '/client/get_providers_locations';
      const res = await api.get(endpoint);
      setMarkers(res.data || []);
    } catch (err) {
      console.error('Failed to fetch locations:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleCalloutPress = (marker: MapMarker) => {
    if (!isProvider) {
      router.push(`/provider/${marker.id}` as any);
    }
  };

  return (
    <View style={styles.container}>
      <Stack.Screen options={{ headerShown: true, title: 'Map' }} />

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color="#3f4a36" />
        </View>
      ) : (
        <>
          <MapView
            ref={mapRef}
            style={styles.map}
            initialRegion={region}
            showsUserLocation
            showsMyLocationButton
          >
            {markers.map((marker) => (
              <Marker
                key={marker.id}
                coordinate={{
                  latitude: marker.lat,
                  longitude: marker.lng,
                }}
                pinColor={marker.online ? '#22c55e' : '#9ca3af'}
              >
                <Callout onPress={() => handleCalloutPress(marker)}>
                  <View style={styles.callout}>
                    <Text style={styles.calloutName}>{marker.name}</Text>
                    <Text style={styles.calloutStatus}>
                      {marker.online ? 'Online' : 'Offline'}
                    </Text>
                    {!isProvider && (
                      <Text style={styles.calloutLink}>View Profile</Text>
                    )}
                  </View>
                </Callout>
              </Marker>
            ))}
          </MapView>

          <TouchableOpacity
            style={styles.listViewBtn}
            onPress={() => router.back()}
            activeOpacity={0.8}
          >
            <Text style={styles.listViewBtnText}>List View</Text>
          </TouchableOpacity>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f9fafb',
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  map: {
    flex: 1,
  },
  callout: {
    padding: 8,
    minWidth: 120,
    alignItems: 'center',
  },
  calloutName: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1f2937',
    marginBottom: 4,
  },
  calloutStatus: {
    fontSize: 12,
    color: '#6b7280',
    marginBottom: 4,
  },
  calloutLink: {
    fontSize: 12,
    color: '#3f4a36',
    fontWeight: '600',
  },
  listViewBtn: {
    position: 'absolute',
    bottom: 40,
    alignSelf: 'center',
    backgroundColor: '#3f4a36',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 25,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 5,
  },
  listViewBtnText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
});

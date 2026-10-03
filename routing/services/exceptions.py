class RoutingError(Exception):
    pass

class GeocodingError(RoutingError):
    pass

class RouteProviderError(RoutingError):
    pass

class FuelOptimizationError(Exception):
    pass

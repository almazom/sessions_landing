import { LatestSessionSummary, Session, SessionRoute } from '@/lib/api';

type RouteCarrier = {
  route?: SessionRoute;
};

export function getSessionRoute(target?: RouteCarrier | null): SessionRoute | null {
  return target?.route || null;
}

export function getSessionRouteHref(target?: RouteCarrier | null): string | null {
  return getSessionRoute(target)?.href || null;
}

export function getSessionRouteKey(target?: RouteCarrier | null): string {
  const route = getSessionRoute(target);
  if (!route) {
    return '';
  }
  return `${route.harness}:${route.id}`;
}

export function matchesRoute(target: Session | LatestSessionSummary | null | undefined, key: string): boolean {
  return Boolean(key) && getSessionRouteKey(target) === key;
}

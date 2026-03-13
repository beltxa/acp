package com.cooperate.poker.dealer.ui;

import com.vaadin.flow.server.VaadinSession;

public final class DealerSessionState {
  private static final String AUTHENTICATED_USER_KEY = DealerSessionState.class.getName() + ".authenticatedUser";

  private DealerSessionState() {
  }

  public static boolean isAuthenticated() {
    return getAuthenticatedUsername() != null;
  }

  public static String getAuthenticatedUsername() {
    VaadinSession session = VaadinSession.getCurrent();
    if (session == null) {
      return null;
    }
    Object username = session.getAttribute(AUTHENTICATED_USER_KEY);
    return username instanceof String value && !value.isBlank() ? value : null;
  }

  public static void setAuthenticatedUsername(String username) {
    VaadinSession session = VaadinSession.getCurrent();
    if (session != null) {
      session.setAttribute(AUTHENTICATED_USER_KEY, username);
    }
  }

  public static void clear() {
    VaadinSession session = VaadinSession.getCurrent();
    if (session != null) {
      session.setAttribute(AUTHENTICATED_USER_KEY, null);
    }
  }
}

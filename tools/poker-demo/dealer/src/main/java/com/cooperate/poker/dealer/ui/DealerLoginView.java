package com.cooperate.poker.dealer.ui;

import com.cooperate.poker.dealer.security.DealerAuthService;
import com.vaadin.flow.component.Html;
import com.vaadin.flow.component.Key;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.Image;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.notification.Notification;
import com.vaadin.flow.component.notification.NotificationVariant;
import com.vaadin.flow.component.orderedlayout.FlexComponent;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.textfield.PasswordField;
import com.vaadin.flow.component.textfield.TextField;
import com.vaadin.flow.router.BeforeEnterEvent;
import com.vaadin.flow.router.BeforeEnterObserver;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;

@Route("login")
@PageTitle("Poker Dealer Login")
public class DealerLoginView extends VerticalLayout implements BeforeEnterObserver {
  private final DealerAuthService authService;
  private final TextField username = new TextField("Username");
  private final PasswordField password = new PasswordField("Password");

  public DealerLoginView(DealerAuthService authService) {
    this.authService = authService;

    setSizeFull();
    addClassName("workbench-login-view");
    setAlignItems(FlexComponent.Alignment.CENTER);
    setJustifyContentMode(JustifyContentMode.CENTER);

    H2 title = new H2("Poker Dealer Login");
    title.addClassName("workbench-login-title");
    Paragraph subtitle = new Paragraph("Sign in with your dealer credentials.");
    subtitle.addClassName("workbench-login-subtitle");
    Image logo = new Image("/images/co-operate-logo.png", "Co-operate");
    logo.addClassName("workbench-login-logo");

    username.setRequired(true);
    username.setClearButtonVisible(true);
    username.setAutofocus(true);
    username.setWidthFull();

    password.setRequired(true);
    password.setWidthFull();
    password.addKeyPressListener(Key.ENTER, event -> authenticate());

    Button signIn = new Button("Sign In", event -> authenticate());
    signIn.addThemeVariants(ButtonVariant.LUMO_PRIMARY);
    signIn.setWidthFull();

    VerticalLayout form = new VerticalLayout(username, password, signIn);
    form.addClassName("workbench-login-form");
    form.setPadding(false);
    form.setSpacing(true);
    form.setWidthFull();

    VerticalLayout card = new VerticalLayout(logo, title, subtitle, form);
    card.addClassName("workbench-login-card");
    card.setPadding(false);
    card.setSpacing(true);
    card.setAlignItems(FlexComponent.Alignment.STRETCH);
    card.setWidth("min(440px, 92vw)");

    add(new Html(buildLoginStyles()), card);
  }

  @Override
  public void beforeEnter(BeforeEnterEvent event) {
    if (!authService.isEnabled()) {
      event.forwardTo("");
      return;
    }
    if (DealerSessionState.isAuthenticated()) {
      event.forwardTo("");
    }
  }

  private void authenticate() {
    String authenticatedUsername = authService.authenticate(username.getValue(), password.getValue());
    if (authenticatedUsername == null) {
      Notification notification = Notification.show(
          "Login failed. Check username/password.",
          3500,
          Notification.Position.TOP_CENTER
      );
      notification.addThemeVariants(NotificationVariant.LUMO_ERROR);
      return;
    }

    DealerSessionState.setAuthenticatedUsername(authenticatedUsername);
    Notification success = Notification.show("Signed in as " + authenticatedUsername, 2000, Notification.Position.TOP_CENTER);
    success.addThemeVariants(NotificationVariant.LUMO_SUCCESS);
    getUI().ifPresent(ui -> ui.navigate(""));
  }

  private static String buildLoginStyles() {
    return """
        <style>
          html {
            --wb-bg-top: #f4f8ff;
            --wb-bg-bottom: #e6eefb;
            --wb-surface: rgba(255, 255, 255, 0.9);
            --wb-border: #c9d8ee;
            --wb-text: #162641;
            --wb-muted: #4e6283;
            --wb-shadow: 0 16px 28px rgba(20, 45, 86, 0.08);
          }

          html,
          body {
            background:
              radial-gradient(circle at 15% 10%, rgba(96, 147, 229, 0.2), transparent 40%),
              linear-gradient(160deg, var(--wb-bg-top), var(--wb-bg-bottom));
          }

          .workbench-login-view {
            padding: var(--lumo-space-m);
          }

          .workbench-login-card {
            border: 1px solid var(--wb-border);
            border-radius: 16px;
            background: var(--wb-surface);
            box-shadow: var(--wb-shadow);
            padding: clamp(1rem, 3vw, 1.5rem);
          }

          .workbench-login-title {
            margin: 0;
            color: var(--wb-text);
            text-align: center;
          }

          .workbench-login-subtitle {
            margin: 0;
            color: var(--wb-muted);
            text-align: center;
          }

          .workbench-login-logo {
            display: block;
            width: min(240px, 64vw);
            height: auto;
            margin: 0 auto 0.2rem;
          }

          .workbench-login-form {
            margin-top: 0.35rem;
            gap: 0.65rem;
          }
        </style>
        """;
  }
}

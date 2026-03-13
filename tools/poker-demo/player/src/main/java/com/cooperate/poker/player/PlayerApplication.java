package com.cooperate.poker.player;

import com.cooperate.poker.player.config.PlayerProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableConfigurationProperties(PlayerProperties.class)
@EnableScheduling
public class PlayerApplication {
  public static void main(String[] args) {
    SpringApplication.run(PlayerApplication.class, args);
  }
}

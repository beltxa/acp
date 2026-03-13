package com.cooperate.chessplayer;

import com.cooperate.chessplayer.config.ChessPlayerProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
@EnableConfigurationProperties(ChessPlayerProperties.class)
public class ChessPlayerApplication {
  public static void main(String[] args) {
    SpringApplication.run(ChessPlayerApplication.class, args);
  }
}

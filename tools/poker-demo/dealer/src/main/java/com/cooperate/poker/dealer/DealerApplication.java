package com.cooperate.poker.dealer;

import com.cooperate.poker.dealer.config.DealerProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(DealerProperties.class)
public class DealerApplication {
  public static void main(String[] args) {
    SpringApplication.run(DealerApplication.class, args);
  }
}

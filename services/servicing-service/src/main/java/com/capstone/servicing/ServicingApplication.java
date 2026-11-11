package com.capstone.servicing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling // Add this annotation
@SpringBootApplication
public class ServicingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ServicingApplication.class, args);
    }
}
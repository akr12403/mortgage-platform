package com.capstone.mortgage.entity;

import jakarta.persistence.*;

import java.util.Arrays;
import java.util.List;
import java.util.UUID;

/** Login identity (M6). Password is a BCrypt hash; roles are a comma-separated list of standards.md role codes. */
@Entity
@Table(name = "app_user")
public class AppUser {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(nullable = false, unique = true)
    private String username;

    @Column(name = "password_hash", nullable = false)
    private String passwordHash;

    @Column(nullable = false)
    private String roles;

    @Column(nullable = false)
    private boolean enabled = true;

    public AppUser() {}

    public AppUser(String username, String passwordHash, List<String> roles) {
        this.username = username;
        this.passwordHash = passwordHash;
        this.roles = String.join(",", roles);
    }

    public List<String> roleList() {
        return Arrays.stream(roles.split(",")).map(String::trim).filter(r -> !r.isEmpty()).toList();
    }

    public UUID getId() { return id; }
    public String getUsername() { return username; }
    public String getPasswordHash() { return passwordHash; }
    public void setPasswordHash(String passwordHash) { this.passwordHash = passwordHash; }
    public String getRoles() { return roles; }
    public boolean isEnabled() { return enabled; }
    public void setEnabled(boolean enabled) { this.enabled = enabled; }
}

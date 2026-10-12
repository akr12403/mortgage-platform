package com.capstone.mortgage.controller;

import com.capstone.mortgage.entity.Borrower;
import com.capstone.mortgage.repository.BorrowerRepository;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/borrowers")
public class BorrowerController {

    private final BorrowerRepository borrowerRepository;

    public BorrowerController(BorrowerRepository borrowerRepository) {
        this.borrowerRepository = borrowerRepository;
    }

    @PostMapping
    public ResponseEntity<Borrower> createBorrower(@Valid @RequestBody Borrower borrower) {
        Borrower saved = borrowerRepository.save(borrower);
        return new ResponseEntity<>(saved, HttpStatus.CREATED);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Borrower> getBorrowerById(@PathVariable Long id) {
        Borrower borrower = borrowerRepository.findById(id)
                .orElseThrow(() -> new RuntimeException("Borrower not found with id: " + id));
        return ResponseEntity.ok(borrower);
    }
}
package com.capstone.mortgage.controller;

import com.capstone.mortgage.dto.BorrowerRequest;
import com.capstone.mortgage.dto.BorrowerResponse;
import com.capstone.mortgage.entity.Borrower;
import com.capstone.mortgage.exception.BusinessRuleException;
import com.capstone.mortgage.exception.ResourceNotFoundException;
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
    public ResponseEntity<BorrowerResponse> createBorrower(@Valid @RequestBody BorrowerRequest request) {
        if (borrowerRepository.findByBorrowerExternalId(request.borrowerExternalId()).isPresent()) {
            throw BusinessRuleException.conflict("BORROWER_ALREADY_EXISTS",
                    "Borrower " + request.borrowerExternalId() + " already exists");
        }
        Borrower borrower = new Borrower();
        borrower.setBorrowerExternalId(request.borrowerExternalId());
        borrower.setFirstName(request.firstName());
        borrower.setLastName(request.lastName());
        borrower.setEmail(request.email());
        borrower.setPhone(request.phone());
        borrower.setDateOfBirth(request.dateOfBirth());
        Borrower saved = borrowerRepository.save(borrower);
        return new ResponseEntity<>(BorrowerResponse.from(saved), HttpStatus.CREATED);
    }

    @GetMapping("/{borrowerExternalId}")
    public ResponseEntity<BorrowerResponse> getBorrowerByExternalId(@PathVariable String borrowerExternalId) {
        Borrower borrower = borrowerRepository.findByBorrowerExternalId(borrowerExternalId)
                .orElseThrow(() -> ResourceNotFoundException.borrower(borrowerExternalId));
        return ResponseEntity.ok(BorrowerResponse.from(borrower));
    }
}
